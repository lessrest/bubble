from dataclasses import field, dataclass

from invoke.tasks import task
from invoke.context import Context


@dataclass
class Command:
    args: list[str | dict[str, bool | str]] = field(default_factory=list)

    def append(self, arg: str | dict[str, bool | str]):
        self.args.append(arg)
        return self

    def __str__(self):
        line = ""
        for arg in self.args:
            if isinstance(arg, dict):
                for flag, value in arg.items():
                    if value:
                        line += f" {flag}"
                        if value is not True:
                            line += f" {value}"
            else:
                line += f" {arg}"
        return line


def sh(*args: str | dict[str, bool | str]) -> Command:
    return Command(list(args))


def run(c: Context, command: Command, **kwargs):
    if "echo" not in kwargs:
        kwargs["echo"] = True
    if "pty" not in kwargs:
        kwargs["pty"] = True
    c.run(str(command), **kwargs)


@task
def css(c: Context, watch=False):
    """Build Tailwind CSS."""
    src = "./src/bubble/http/static/css/input.css"
    dst = "./src/bubble/http/static/css/output.css"
    cmd = sh("bunx tailwindcss", {"-i": src, "-o": dst, "--watch": watch})
    run(c, cmd)


@task
def test(c: Context, coverage=False):
    """Run tests."""
    run(c, sh("pytest", {"--cov": coverage}))
    if coverage:
        c.run("coverage report")
        c.run("coverage html")


@task
def server(c: Context, watch=True, bind="127.0.0.1:2026"):
    """Run Bubble web server."""
    if not watch:
        # If not watching, just run the server directly
        run(
            c,
            sh(
                "bubble",
                "serve",
                {"--bind": bind},
            ),
            pty=True,
        )
    else:
        # Use watchfiles to restart on changes
        run(
            c,
            sh(
                "watchfiles",
                "--filter",
                "python",
                f"'bubble serve --bind {bind}'",
                "./src",
                "./swash",
            ),
            pty=True,
        )


@task
def shell(c: Context):
    """Run Bubble shell."""
    run(c, sh("python -m bubble"), pty=True, echo=True)


@task
def clean(c: Context):
    """Clean up."""
    patterns = [
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        "dist",
        "*.egg-info",
        ".venv",
        ".coverage",
    ]
    for pattern in patterns:
        run(c, sh("rm -rf", pattern))
    run(c, sh("git status"))


@task
def fmt(c: Context):
    """Format imports using Ruff."""
    run(c, sh("ruff", "check", "--select", "I", "--fix", "."))
