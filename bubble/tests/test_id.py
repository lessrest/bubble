import pytest
import re
from rdflib import Namespace
from bubble.id import Mint

@pytest.fixture
def mint():
    return Mint()

def test_fresh_token_format(mint):
    """Test that fresh_token generates valid base32 strings"""
    token = mint.fresh_token()
    # Should be 32 chars of base32 (no padding)
    assert len(token) == 32
    assert re.match(r'^[a-z2-7]+$', token) is not None

def test_fresh_token_uniqueness(mint):
    """Test that fresh_tokens are unique"""
    tokens = [mint.fresh_token() for _ in range(100)]
    assert len(set(tokens)) == 100

def test_fresh_secure_iri(mint):
    """Test secure IRI generation with namespace"""
    ns = Namespace("https://test.example/")
    iri = mint.fresh_secure_iri(ns)
    
    # IRI should start with namespace
    assert str(iri).startswith("https://test.example/")
    
    # Rest should be a valid token
    token = str(iri)[len("https://test.example/"):]
    assert len(token) == 32
    assert re.match(r'^[a-z2-7]+$', token) is not None

def test_fresh_casual_iri(mint):
    """Test casual IRI generation with namespace"""
    ns = Namespace("https://test.example/")
    iri = mint.fresh_casual_iri(ns)
    
    # IRI should start with namespace
    assert str(iri).startswith("https://test.example/")
    
    # Rest should be a valid XID
    token = str(iri)[len("https://test.example/"):]
    assert len(token) == 20
    assert re.match(r'^[a-z0-9]+$', token) is not None

def test_fresh_id_format(mint):
    """Test fresh_id generates valid XID strings"""
    id = mint.fresh_id()
    # XID is 20 chars
    assert len(id) == 20
    # Should be lowercase base32
    assert re.match(r'^[a-z0-9]+$', id) is not None

def test_machine_id_format(mint):
    """Test machine_id generates valid base32 strings"""
    id = mint.machine_id()
    # Should be 32 chars of base32 (no padding)
    assert len(id) == 32
    assert re.match(r'^[a-z2-7]+$', id) is not None

def test_machine_id_consistency(mint):
    """Test machine_id returns consistent values"""
    id1 = mint.machine_id()
    id2 = mint.machine_id()
    assert id1 == id2
