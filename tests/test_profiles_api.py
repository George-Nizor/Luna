import io

import numpy as np
import soundfile as sf


def audio_bytes(seconds=2):
    buffer = io.BytesIO()
    sf.write(buffer, np.zeros(22050 * seconds, dtype=np.float32), 22050, format="WAV")
    return buffer.getvalue()


def test_health_and_profile_api(app_client):
    client, app = app_client
    assert client.get("/api/health").json()["status"] == "ok"
    response = client.post(
        "/api/profiles",
        files={"reference_audio": ("reference.wav", audio_bytes(), "audio/wav")},
        data={"name": "Narrator", "language": "English", "reference_transcript": "Hello.", "consent_confirmed": "true"},
    )
    assert response.status_code == 200
    profile_id = response.json()["id"]
    assert client.get("/api/profiles").json()["profiles"][0]["id"] == profile_id
    assert client.get(f"/api/profiles/{profile_id}/reference?token={app.state.token}").status_code == 200
    assert client.delete(f"/api/profiles/{profile_id}").status_code == 200


def test_missing_consent_and_invalid_token(app_client):
    client, _ = app_client
    response = client.post(
        "/api/profiles",
        files={"reference_audio": ("reference.wav", audio_bytes(), "audio/wav")},
        data={"name": "Narrator", "language": "English", "reference_transcript": "Hello.", "consent_confirmed": "false"},
    )
    assert response.status_code == 422
    client.headers["X-Local-Token"] = "wrong"
    assert client.get("/api/profiles").status_code == 403
