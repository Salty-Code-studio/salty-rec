// saltyrec-helper: the native bits Python can't do well.
//   devices                      JSON list of displays and microphones
//   record --display ID --out F  ScreenCaptureKit recording (screen, mic, computer sound) until "q" on stdin
//   hotkeys                      global shortcuts, prints one word per press
//   permission                   asks macOS for Screen Recording access, prints granted or denied
//   av-permission                asks for camera and microphone access, prints "camera X mic Y"
import AppKit
import AVFoundation
import Carbon
import Foundation
import ScreenCaptureKit

func say(_ s: String) {
    FileHandle.standardOutput.write((s + "\n").data(using: .utf8)!)
}

func fail(_ s: String, _ code: Int32 = 1) -> Never {
    FileHandle.standardError.write(("error: " + s + "\n").data(using: .utf8)!)
    exit(code)
}

func arg(_ name: String) -> String? {
    let a = CommandLine.arguments
    guard let i = a.firstIndex(of: name), i + 1 < a.count else { return nil }
    return a[i + 1]
}

/// Calls `onQuit` when the parent writes "q" or goes away.
func watchStdin(_ onQuit: @escaping () -> Void) {
    Thread {
        while let line = readLine() {
            if line.trimmingCharacters(in: .whitespaces) == "q" { break }
        }
        onQuit()
    }.start()
}

// MARK: devices

func devices() {
    Task {
        do {
            let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
            var names: [UInt32: String] = [:]
            for s in NSScreen.screens {
                if let n = s.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber {
                    names[n.uint32Value] = s.localizedName
                }
            }
            let displays = content.displays.map { d -> [String: Any] in
                ["id": d.displayID, "width": d.width, "height": d.height,
                 "name": names[d.displayID] ?? "Display \(d.displayID)",
                 "x": d.frame.origin.x, "y": d.frame.origin.y]
            }
            let me = getpid(), parent = getppid()
            let windows = content.windows.filter {
                $0.windowLayer == 0 && $0.isOnScreen && $0.frame.width >= 200 && $0.frame.height >= 150
                    && !($0.title ?? "").isEmpty && $0.owningApplication != nil
                    && $0.owningApplication!.processID != me && $0.owningApplication!.processID != parent
            }.map { w -> [String: Any] in
                ["id": w.windowID, "app": w.owningApplication!.applicationName, "pid": w.owningApplication!.processID,
                 "title": w.title ?? "", "x": w.frame.origin.x, "y": w.frame.origin.y,
                 "width": w.frame.width, "height": w.frame.height]
            }
            let mics = AVCaptureDevice.DiscoverySession(deviceTypes: [.microphone, .external],
                                                        mediaType: .audio, position: .unspecified).devices
                .map { ["uid": $0.uniqueID, "name": $0.localizedName] }
            let data = try JSONSerialization.data(withJSONObject: ["displays": displays, "mics": mics, "windows": windows])
            say(String(data: data, encoding: .utf8)!)
            exit(0)
        } catch {
            fail("\(error.localizedDescription)", 2)
        }
    }
    dispatchMain()
}

// MARK: record

/// One file per segment, written straight from the live stream buffers: video, computer sound, mic.
final class Segment {
    let path: String
    let writer: AVAssetWriter
    let video: AVAssetWriterInput
    var system: AVAssetWriterInput?
    var mic: AVAssetWriterInput?
    var started = false
    var last = CMTime.invalid

    init(path: String, width: Int, height: Int, system wantSystem: Bool, mic wantMic: Bool) throws {
        self.path = path
        try? FileManager.default.removeItem(atPath: path)
        writer = try AVAssetWriter(outputURL: URL(fileURLWithPath: path), fileType: .mp4)
        writer.shouldOptimizeForNetworkUse = true
        video = AVAssetWriterInput(mediaType: .video, outputSettings: [
            AVVideoCodecKey: AVVideoCodecType.h264, AVVideoWidthKey: width, AVVideoHeightKey: height,
            AVVideoCompressionPropertiesKey: [
                AVVideoAverageBitRateKey: 10_000_000, AVVideoExpectedSourceFrameRateKey: 30,
                AVVideoMaxKeyFrameIntervalKey: 60, AVVideoProfileLevelKey: AVVideoProfileLevelH264HighAutoLevel]])
        video.expectsMediaDataInRealTime = true
        writer.add(video)
        if wantSystem {
            let i = AVAssetWriterInput(mediaType: .audio, outputSettings: [
                AVFormatIDKey: kAudioFormatMPEG4AAC, AVSampleRateKey: 48000, AVNumberOfChannelsKey: 2,
                AVEncoderBitRateKey: 160000])
            i.expectsMediaDataInRealTime = true
            writer.add(i)
            system = i
        }
        if wantMic {
            let i = AVAssetWriterInput(mediaType: .audio, outputSettings: [
                AVFormatIDKey: kAudioFormatMPEG4AAC, AVSampleRateKey: 48000, AVNumberOfChannelsKey: 1,
                AVEncoderBitRateKey: 128000])
            i.expectsMediaDataInRealTime = true
            writer.add(i)
            mic = i
        }
    }

    func start(at t: CMTime) {
        guard !started, writer.startWriting() else { return }
        writer.startSession(atSourceTime: t)
        started = true
    }

    func append(_ buf: CMSampleBuffer, to input: AVAssetWriterInput?) {
        guard started, let input, writer.status == .writing, input.isReadyForMoreMediaData else { return }
        input.append(buf)
    }
}

final class Recording: NSObject, SCStreamDelegate, SCStreamOutput {
    // The stream stays warm for the whole session; segments open and close instantly on command.
    var stream: SCStream?
    let queue = DispatchQueue(label: "frames")
    var wantMic = false
    var wantSystem = false
    var width = 0
    var height = 0
    var segment: Segment?          // touched on `queue`
    var lastFrame: CMSampleBuffer? // last frame with pixels, reused when the screen is still

    func setup() async {
        let displayID = UInt32(arg("--display") ?? "") ?? 0
        let mic = arg("--mic") ?? "none"
        wantMic = mic != "none"
        wantSystem = arg("--system") == "1"
        let parent = Int32(arg("--parent") ?? "") ?? getppid()
        let hidePrefix = arg("--hide-title") ?? "salty-rec-hide"
        let maxWidth = Int(arg("--max-width") ?? "") ?? 2560
        do {
            let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: false)
            // --rect x,y,w,h in global points: record just that part of the screen (an area, or a window's frame)
            let rect: CGRect? = arg("--rect").flatMap { s in
                let n = s.split(separator: ",").compactMap { Double($0) }
                return n.count == 4 ? CGRect(x: n[0], y: n[1], width: n[2], height: n[3]) : nil
            }
            let byRect = rect.flatMap { r in content.displays.first { $0.frame.contains(CGPoint(x: r.midX, y: r.midY)) } }
            guard let display = byRect ?? content.displays.first(where: { $0.displayID == displayID }) ?? content.displays.first
            else { fail("no display", 3) }
            let hidden = content.windows.filter {
                $0.owningApplication?.processID == parent && ($0.title ?? "").hasPrefix(hidePrefix)
            }
            let filter = SCContentFilter(display: display, excludingWindows: hidden)
            let scale = CGFloat(filter.pointPixelScale)
            var source: CGRect? = nil
            if let r = rect {
                source = r.offsetBy(dx: -display.frame.origin.x, dy: -display.frame.origin.y)
                    .intersection(CGRect(origin: .zero, size: display.frame.size))
            }
            let size = source?.size ?? filter.contentRect.size
            var w = Int(size.width * scale), h = Int(size.height * scale)
            if w > maxWidth { h = h * maxWidth / w; w = maxWidth }
            width = w / 2 * 2
            height = h / 2 * 2
            let cfg = SCStreamConfiguration()
            cfg.width = width
            cfg.height = height
            if let src = source { cfg.sourceRect = src }
            cfg.minimumFrameInterval = CMTime(value: 1, timescale: 30)
            cfg.queueDepth = 8
            cfg.showsCursor = true
            cfg.showMouseClicks = true
            cfg.capturesAudio = wantSystem
            cfg.excludesCurrentProcessAudio = true
            cfg.sampleRate = 48000
            cfg.channelCount = 2
            if wantMic {
                cfg.captureMicrophone = true
                cfg.microphoneCaptureDeviceID = mic
            }
            let stream = SCStream(filter: filter, configuration: cfg, delegate: self)
            try stream.addStreamOutput(self, type: .screen, sampleHandlerQueue: queue)
            if wantSystem { try stream.addStreamOutput(self, type: .audio, sampleHandlerQueue: queue) }
            if wantMic { try stream.addStreamOutput(self, type: .microphone, sampleHandlerQueue: queue) }
            try await stream.startCapture()
            self.stream = stream
            say("ready \(hidden.count)")
        } catch {
            fail(error.localizedDescription, 4)
        }
    }

    static func now() -> CMTime { CMClockGetTime(CMClockGetHostTimeClock()) }

    static func restamp(_ buf: CMSampleBuffer, _ t: CMTime) -> CMSampleBuffer? {
        var timing = CMSampleTimingInfo(duration: .invalid, presentationTimeStamp: t, decodeTimeStamp: .invalid)
        var out: CMSampleBuffer?
        CMSampleBufferCreateCopyWithNewTiming(allocator: nil, sampleBuffer: buf, sampleTimingEntryCount: 1,
                                              sampleTimingArray: &timing, sampleBufferOut: &out)
        return out
    }

    func begin(_ path: String) {
        queue.sync {
            guard segment == nil else { return }
            do {
                let seg = try Segment(path: path, width: width, height: height, system: wantSystem, mic: wantMic)
                let t = Recording.now()
                seg.start(at: t)
                if let f = lastFrame, let copy = Recording.restamp(f, t) {
                    seg.append(copy, to: seg.video)
                    seg.last = t
                }
                segment = seg
                say("started \(path)")
            } catch {
                fail("cannot write \(path): \(error.localizedDescription)", 6)
            }
        }
    }

    /// Closes the current segment and blocks until the file is complete.
    func end() {
        var seg: Segment?
        queue.sync {
            seg = segment
            segment = nil
            guard let s = seg, s.started else { return }
            // hold the last image until the moment of the pause, so a still screen keeps its length
            let t = Recording.now()
            if let f = lastFrame, let copy = Recording.restamp(f, t) { s.append(copy, to: s.video) }
            s.video.markAsFinished()
            s.system?.markAsFinished()
            s.mic?.markAsFinished()
            s.writer.endSession(atSourceTime: t)
        }
        guard let s = seg else { return }
        let done = DispatchSemaphore(value: 0)
        s.writer.finishWriting { done.signal() }
        _ = done.wait(timeout: .now() + 10)
        if s.writer.status == .failed {
            FileHandle.standardError.write("write failed: \(s.writer.error?.localizedDescription ?? "")\n".data(using: .utf8)!)
        }
        say("segment none \(s.path)")
    }

    func shutdown() -> Never {
        end()
        let done = DispatchSemaphore(value: 0)
        Task { try? await stream?.stopCapture(); done.signal() }
        _ = done.wait(timeout: .now() + 5)
        say("finished")
        exit(0)
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer buf: CMSampleBuffer, of type: SCStreamOutputType) {
        guard buf.isValid else { return }
        switch type {
        case .screen:
            guard let info = (CMSampleBufferGetSampleAttachmentsArray(buf, createIfNecessary: false) as? [[SCStreamFrameInfo: Any]])?.first,
                  let raw = info[.status] as? Int, SCFrameStatus(rawValue: raw) == .complete,
                  CMSampleBufferGetImageBuffer(buf) != nil else { return }
            lastFrame = buf
            if let s = segment {
                let pts = CMSampleBufferGetPresentationTimeStamp(buf)
                if !s.last.isValid || CMTimeCompare(pts, s.last) > 0 {
                    s.append(buf, to: s.video)
                    s.last = pts
                }
            }
        case .audio:
            segment.map { $0.append(buf, to: $0.system) }
        case .microphone:
            segment.map { $0.append(buf, to: $0.mic) }
        @unknown default:
            break
        }
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        fail("stream stopped: \(error.localizedDescription)", 5)
    }
}

/// stdin commands: "resume <path>" starts a segment, "pause" closes it, "q" closes and exits.
func record() {
    let r = Recording()
    _ = NSApplication.shared
    Task {
        await r.setup()
        if let first = arg("--out") { r.begin(first) }
        Thread {
            while let line = readLine() {
                let parts = line.split(separator: " ", maxSplits: 1).map(String.init)
                switch parts.first {
                case "resume": if parts.count == 2 { r.begin(parts[1]) }
                case "pause": r.end()
                case "q": r.shutdown()
                default: break
                }
            }
            r.shutdown()
        }.start()
    }
    dispatchMain()
}

// MARK: hotkeys

let hotkeyNames: [UInt32: String] = [1: "record", 2: "pause", 3: "draw", 4: "cancel"]

func hotkeys() {
    let app = NSApplication.shared
    app.setActivationPolicy(.prohibited)
    var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
    InstallEventHandler(GetApplicationEventTarget(), { _, event, _ in
        var hk = EventHotKeyID()
        GetEventParameter(event, EventParamName(kEventParamDirectObject), EventParamType(typeEventHotKeyID),
                          nil, MemoryLayout<EventHotKeyID>.size, nil, &hk)
        if let name = hotkeyNames[hk.id] { say(name) }
        return noErr
    }, 1, &spec, nil, nil)
    let mods = UInt32(optionKey | shiftKey)
    let keys: [(Int, UInt32)] = [(kVK_ANSI_R, 1), (kVK_ANSI_P, 2), (kVK_ANSI_D, 3), (kVK_ANSI_X, 4)]
    for (key, id) in keys {
        var ref: EventHotKeyRef?
        let status = RegisterEventHotKey(UInt32(key), mods, EventHotKeyID(signature: OSType(0x5352_4543), id: id),
                                         GetApplicationEventTarget(), 0, &ref)
        if status != noErr { FileHandle.standardError.write("hotkey \(id) taken\n".data(using: .utf8)!) }
    }
    say("ready")
    watchStdin { exit(0) }
    app.run()
}

switch CommandLine.arguments.dropFirst().first {
case "devices": devices()
case "record": record()
case "hotkeys": hotkeys()
case "av-permission":
    func ask(_ type: AVMediaType) -> Bool {
        switch AVCaptureDevice.authorizationStatus(for: type) {
        case .authorized: return true
        case .notDetermined:
            let done = DispatchSemaphore(value: 0)
            var ok = false
            AVCaptureDevice.requestAccess(for: type) { ok = $0; done.signal() }
            done.wait()
            return ok
        default: return false
        }
    }
    let cam = ask(.video), mic = ask(.audio)
    say("camera \(cam ? "granted" : "denied") mic \(mic ? "granted" : "denied")")
case "permission": say(CGPreflightScreenCaptureAccess() || CGRequestScreenCaptureAccess() ? "granted" : "denied")
default: fail("usage: saltyrec-helper devices|record|hotkeys|permission")
}
