from dataclasses import dataclass, field
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
    src = "./src/bubble/static/css/input.css"
    dst = "./src/bubble/static/css/output.css"
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
def server(c: Context, watch=True, debug=True, bind="0.0.0.0:2024"):
    """Run Bubble web server."""
    run(
        c,
        sh(
            "hypercorn",
            {"-k": "trio"},
            {"--reload": watch},
            {"--debug": debug},
            {"--bind": bind},
            "bubble.http:app",
        ),
        pty=True,
        echo=True,
    )


@task
def shell(c: Context):
    """Run Bubble shell."""
    run(c, sh("python -m bubble"), pty=True, echo=True)
