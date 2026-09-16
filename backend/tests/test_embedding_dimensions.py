from models.database import DocumentChunk


def test_embedding_dimension_is_derived_without_model_name_rule():
    chunk = DocumentChunk(embedding=[0.0] * 2560)

    assert chunk.embedding_dimension == 2560


def test_clearing_embedding_clears_derived_dimension():
    chunk = DocumentChunk(embedding=[0.0] * 1024)
    chunk.embedding = None

    assert chunk.embedding_dimension is None
