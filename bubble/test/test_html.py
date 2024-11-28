import pytest
import xml.etree.ElementTree as ET

from bubble.html import (
    document,
    tag,
    text,
    attr,
    classes,
    dataset,
    html,
    HypermediaResponse,
    XMLResponse,
)


@pytest.fixture
def doc():
    """Create a new document for testing"""
    with document() as d:
        yield d


def test_basic_document():
    """Test creating a basic document with tags and text"""
    with document() as doc:
        with tag("div"):
            with tag("p"):
                text("Hello World")

    result = doc.to_html(compact=True)
    assert "<div><p>Hello World</p></div>" in result


def test_html_decorators():
    """Test the @html decorator functionality"""

    @html.div(class_="container")
    def my_component():
        with tag("p"):
            text("Content")

    with document() as doc:
        my_component()

    result = doc.to_html(compact=True)
    assert '<div class="container"><p>Content</p></div>' in result


def test_attributes():
    """Test setting various HTML attributes"""
    with document() as doc:
        with tag("input", type="text", required=True, disabled=False):
            pass

    result = doc.to_html(compact=True)
    assert 'type="text"' in result
    assert "required" in result
    assert "disabled" not in result


def test_classes():
    """Test adding CSS classes"""
    with document() as doc:
        with tag("div"):
            classes("foo", "bar")
            text("Content")

    result = doc.to_html()
    assert '<div class="foo bar">\n Content\n</div>\n' in result


def test_dataset():
    """Test adding data attributes"""
    with document() as doc:
        with tag("div"):
            dataset({"test": "value", "other": "123"})

    result = doc.to_html()
    assert 'data-test="value"' in result
    assert 'data-other="123"' in result


def test_nested_tags():
    """Test nesting multiple tags"""
    with document() as doc:
        with tag("div"):
            with tag("header"):
                text("Title")
            with tag("main"):
                with tag("p"):
                    text("Content")
            with tag("footer"):
                text("Footer")

    expected = """\
<div>
 <header>
  Title
 </header>
 <main>
  <p>
   Content
  </p>
 </main>
 <footer>
  Footer
 </footer>
</div>
"""

    assert doc.to_html() == expected


def test_fragment_xml():
    """Test XML serialization of fragments"""
    with document() as doc:
        with tag("root"):
            with tag("child"):
                text("content")

    xml = doc.to_xml()
    assert "<root><child>content</child></root>" in xml


def test_hypermedia_response():
    """Test HypermediaResponse rendering"""
    with document() as doc:
        with tag("div"):
            text("Test")
        response = HypermediaResponse(content=None)
        rendered = response.render(None)
        assert b"<div>\n Test\n</div>\n" in rendered


def test_xml_response():
    """Test XMLResponse rendering"""
    with document() as doc:
        with tag("root"):
            text("Test")
        response = XMLResponse(content=None)
        rendered = response.render(None)
        assert b"<root>Test</root>" in rendered


def test_attr_modification():
    """Test modifying attributes after creation"""
    with document() as doc:
        with tag("div"):
            attr("id", "test")
            attr("class", "foo")
            attr("data-test", None)  # Should remove attribute
            text("Content")

    result = doc.to_html()
    assert 'id="test"' in result
    assert 'class="foo"' in result
    assert "data-test" not in result


def test_multiple_text_nodes():
    """Test adding multiple text nodes"""
    with document() as doc:
        with tag("p"):
            text("Hello")
            text(" ")
            text("World")

    result = doc.to_html()
    assert "<p>\n Hello World\n</p>\n" in result


def test_exact_html_document():
    """Test creating a complete HTML document with exact output matching"""
    with document() as doc:
        with tag("html"):
            with tag("head"):
                with tag("title"):
                    text("Test Page")
                with tag("meta", charset="utf-8"):
                    pass
            with tag("body", class_="content"):
                with tag("header"):
                    with tag("h1"):
                        text("Welcome")
                with tag("main"):
                    with tag("p", class_="intro"):
                        text("This is a ")
                        with tag("strong"):
                            text("test")
                        text(" page.")
                    with tag("ul"):
                        for item in ["One", "Two", "Three"]:
                            with tag("li"):
                                text(item)

    expected = """\
<html>
 <head>
  <title>
   Test Page
  </title>
  <meta charset="utf-8"/>
 </head>
 <body class="content">
  <header>
   <h1>
    Welcome
   </h1>
  </header>
  <main>
   <p class="intro">
    This is a
    <strong>
     test
    </strong>
    page.
   </p>
   <ul>
    <li>
     One
    </li>
    <li>
     Two
    </li>
    <li>
     Three
    </li>
   </ul>
  </main>
 </body>
</html>
"""

    assert doc.to_html() == expected


def test_pretty_html():
    """Test creating HTML with proper indentation and newlines (default)"""
    with document() as doc:
        with tag("html"):
            with tag("head"):
                with tag("title"):
                    text("Test Page")
            with tag("body"):
                with tag("div", class_="container"):
                    with tag("h1"):
                        text("Hello")
                    with tag("p"):
                        text("This is a test")

    expected = """\
<html>
 <head>
  <title>
   Test Page
  </title>
 </head>
 <body>
  <div class="container">
   <h1>
    Hello
   </h1>
   <p>
    This is a test
   </p>
  </div>
 </body>
</html>
"""

    assert doc.to_html() == expected


def test_elementtree_basics():
    """Demonstrate how ElementTree creates and renders HTML"""
    # Create elements
    root = ET.Element("html")
    head = ET.SubElement(root, "head")
    title = ET.SubElement(head, "title")
    title.text = "Test"

    body = ET.SubElement(root, "body")
    body.set("class", "content")

    p = ET.SubElement(body, "p")
    p.text = "Hello "
    strong = ET.SubElement(p, "strong")
    strong.text = "World"
    strong.tail = "!"

    # Convert to string
    result = ET.tostring(root, encoding="unicode", method="html")
    expected = '<html><head><title>Test</title></head><body class="content"><p>Hello <strong>World</strong>!</p></body></html>'
    assert result == expected
