from datetime import timedelta

import numpy as np
import soundfile as sf

from app.schemas import OutputMetadata
from app.storage import Storage, utc_now


def test_profile_and_output_storage(test_settings, tmp_path):
    storage = Storage(test_settings)
    source = tmp_path / "reference.wav"
    sf.write(source, np.zeros(22050 * 2, dtype=np.float32), 22050)
    profile = storage.create_profile(
        name="Narrator",
        language="English",
        reference_transcript="Hello world.",
        consent_confirmed=True,
        uploaded_path=source,
    )
    assert storage.get_profile(profile.id).name == "Narrator"
    output_id = "00000000-0000-4000-8000-000000000001"
    output_dir, output_path = storage.begin_output(output_id)
    sf.write(output_path, np.zeros(100, dtype=np.float32), 22050)
    metadata = OutputMetadata(
        id=output_id,
        profile_id=profile.id,
        profile_name=profile.name,
        language="English",
        quality="fast",
        model_id="fake",
        text_character_count=5,
        chunk_count=1,
        duration_seconds=100 / 22050,
        created_at=utc_now(),
    )
    storage.save_output_metadata(metadata)
    assert storage.list_outputs()[0].id == output_id
    assert output_dir.exists()


def test_output_retention(test_settings):
    test_settings.output_history_limit = 1
    storage = Storage(test_settings)
    for index in range(2):
        output_id = f"00000000-0000-4000-8000-00000000000{index + 1}"
        storage.begin_output(output_id)
        metadata = OutputMetadata(
            id=output_id,
            profile_id="fixed:qwen",
            profile_name="Qwen",
            language="English",
            quality="fast",
            model_id="fake",
            text_character_count=index,
            chunk_count=1,
            duration_seconds=1,
            created_at=utc_now() + timedelta(seconds=index),
        )
        storage.save_output_metadata(metadata)
    assert len(storage.list_outputs()) == 1
