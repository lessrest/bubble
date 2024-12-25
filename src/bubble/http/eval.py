import io

from contextlib import redirect_stderr, redirect_stdout

from fastapi import Form

from swash.html import (
    HypermediaResponse,
    tag,
    text,
)
from bubble.http.page import base_shell


async def eval_form():
    """Render the Python code evaluation form."""
    with base_shell("Python Evaluator"):
        with tag("div", classes="p-4"):
            with tag("h1", classes="text-2xl font-bold mb-4"):
                text("Python Code Evaluator")

            render_exec_form()

    return HypermediaResponse()


def render_exec_form(code: str = ""):
    with tag(
        "form",
        hx_post="/eval",
        hx_target="this",
        classes="space-y-4",
    ):
        with tag("div"):
            with tag(
                "textarea",
                name="code",
                placeholder="Enter Python code here...",
                classes=[
                    "w-full h-48 p-2 border font-mono",
                    "dark:bg-gray-800 dark:text-white",
                    "dark:border-gray-700 dark:focus:border-blue-500 dark:focus:ring-blue-500 dark:focus:outline-none",
                ],
            ):
                text(code)

        with tag(
            "button",
            type="submit",
            classes=[
                "px-4 py-2 bg-blue-500 text-white hover:bg-blue-600",
                "dark:bg-blue-600 dark:hover:bg-blue-700",
                "dark:text-white",
                "dark:focus:outline-none dark:focus:ring-2 dark:focus:ring-blue-500 dark:focus:ring-offset-2",
                "dark:border-blue-500",
            ],
        ):
            text("Run")


async def eval_code(code: str = Form(...), town=None):
    """Evaluate Python code and return the results."""
    # Capture stdout and stderr
    stdout = io.StringIO()
    stderr = io.StringIO()

    try:
        # Redirect output
        with redirect_stdout(stdout), redirect_stderr(stderr):
            # Execute the code in a restricted environment
            exec_globals = {"print": print}
            exec(code, exec_globals, {"town": town})

        output = stdout.getvalue()
        errors = stderr.getvalue()

        # Format the input form again
        render_exec_form(code)

        # Format the response
        with tag(
            "div", classes="font-mono whitespace-pre-wrap p-4 rounded"
        ):
            if output:
                with tag("div", classes="bg-gray-100 p-2 rounded"):
                    with tag("div", classes="text-sm text-gray-600 mb-1"):
                        text("Output:")
                    text(output)

            if errors:
                with tag("div", classes="bg-red-100 p-2 rounded mt-2"):
                    with tag("div", classes="text-sm text-red-600 mb-1"):
                        text("Errors:")
                    text(errors)

            if not output and not errors:
                with tag("div", classes="text-gray-500 italic"):
                    text("No output")

        # Render the next form
        render_exec_form()

    except Exception as e:
        with tag("div", classes="bg-red-100 p-2 rounded"):
            with tag("div", classes="text-sm text-red-600 mb-1"):
                text("Error:")
            text(str(e))

    return HypermediaResponse()
