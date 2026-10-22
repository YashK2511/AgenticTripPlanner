"""
Unit tests for Phase 3: POI Retrieval and Embeddings.
"""
import pytest
from unittest.mock import patch, MagicMock
from app.services.embedding_service import encode_text, encode_batch, cosine_similarity
from app.agents.poi_retrieval_agent import retrieve_pois
from app.models.schemas import UserProfile, Money, Traveler
from app.models.db_models import POICandidateModel, POIEmbeddingModel
from datetime import date, timedelta


class TestEmbeddingService:
    def test_cosine_similarity_identical(self):
        vec = [1.0, 0.0, 0.0]
        assert cosine_similarity(vec, vec) == pytest.approx(1.0)

    def test_cosine_similarity_orthogonal(self):
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [0.0, 1.0, 0.0]
        assert cosine_similarity(vec_a, vec_b) == pytest.approx(0.0)

    def test_cosine_similarity_opposite(self):
        vec_a = [1.0, 0.5, 0.2]
        vec_b = [-1.0, -0.5, -0.2]
        assert cosine_similarity(vec_a, vec_b) == pytest.approx(-1.0)

    @patch("app.services.embedding_service.SentenceTransformer")
    def test_encode_text(self, mock_st):
        mock_model_instance = MagicMock()
        mock_model_instance.encode.return_value = [0.1, 0.2, 0.3]
        mock_st.return_value = mock_model_instance

        # We must unset the global _model to force lazy load
        import app.services.embedding_service as ems
        old_model = ems._model
        ems._model = None
        try:
            result = encode_text("test")
            assert result == [0.1, 0.2, 0.3]
            mock_model_instance.encode.assert_called_once_with("test", normalize_embeddings=True)
        finally:
            ems._model = old_model


class TestPOIRetrievalAgent:
    @pytest.fixture
    def mock_db(self):
        # Mock database session
        db = MagicMock()

        # Create dummy candidates
        poi1 = POICandidateModel(
            id="1", name="Beach", description="Goa Beach", category="Beach",
            coordinates_lat=15.0, coordinates_lng=73.0,
            cost_range_min=0, cost_range_max=500,
            accessibility_json={"wheelchair_accessible": True},
            evidence_json={"source_id": "test", "source_type": "db", "retrieved_at": "2026-01-01T00:00:00"}
        )
        embed1 = POIEmbeddingModel(poi_id="1", embedding_json=[1.0, 0.0])

        poi2 = POICandidateModel(
            id="2", name="Mountain", description="Goa Hill", category="Nature",
            coordinates_lat=15.1, coordinates_lng=73.1,
            cost_range_min=2000, cost_range_max=5000,
            accessibility_json={"wheelchair_accessible": False},
            evidence_json={"source_id": "test", "source_type": "db", "retrieved_at": "2026-01-01T00:00:00"}
        )
        embed2 = POIEmbeddingModel(poi_id="2", embedding_json=[0.0, 1.0])

        # Mock query chain: query().join().filter().all()
        query_mock = db.query.return_value
        join_mock = query_mock.join.return_value
        filter_mock = join_mock.filter.return_value
        filter_mock.all.return_value = [
            (poi1, embed1),
            (poi2, embed2)
        ]

        return db

    @pytest.fixture
    def sample_profile(self):
        return UserProfile(
            destination="Goa",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=2),
            budget=Money(amount=1000, currency="INR"),  # Low budget
            travelers=[Traveler(id="1", age_group="adult", gender="male", accessibility_needs=["wheelchair"])],
            interests=["beaches"],
            hard_constraints={},
            soft_preferences={"sea view": 0.9},
            missing_fields=[]
        )

    @patch("app.agents.poi_retrieval_agent.encode_text")
    def test_retrieve_pois_filters_hard_constraints(self, mock_encode, mock_db, sample_profile):
        # Query is highly related to Mountain (vec 2)
        mock_encode.return_value = [0.0, 1.0]

        results = retrieve_pois(sample_profile, mock_db)

        # Even though Mountain has highest similarity, it lacks wheelchair access
        # AND its cost_min (2000) > budget (1000). So it should be filtered out.
        assert len(results) == 1
        assert results[0].id == "1"
        assert results[0].name == "Beach"
