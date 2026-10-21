// Salty Rec.app's main executable. A real binary (not a script) keeps the app as the
// "responsible" process, so macOS files Screen Recording, Camera and Mic access under Salty Rec.
#include <fcntl.h>
#include <signal.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/wait.h>
#include <unistd.h>

extern char **environ;
static pid_t child;

static void forward(int sig) { if (child > 0) kill(child, sig); }

int main(void) {
    setenv("PATH", "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin", 1);
    if (chdir(ROOT) != 0) return 1;
    const char *home = getenv("HOME");
    if (home) {                       // keep a log so problems can be diagnosed later
        char path[1024];
        snprintf(path, sizeof path, "%s/Library/Logs/Salty Rec.log", home);
        int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
        if (fd >= 0) { dup2(fd, 1); dup2(fd, 2); close(fd); }
    }
    char *argv[] = {ROOT "/.venv/bin/python", "-m", "saltyrec", NULL};
    signal(SIGTERM, forward);
    signal(SIGINT, forward);
    signal(SIGHUP, forward);
    if (posix_spawn(&child, argv[0], NULL, NULL, argv, environ) != 0) return 1;
    int status = 0;
    while (waitpid(child, &status, 0) < 0) {}
    return WIFEXITED(status) ? WEXITSTATUS(status) : 1;
}
