from .test_profiles_api import audio_bytes


def make_profile(client):
    return client.post(
        "/api/profiles",
        files={"reference_audio": ("reference.wav", audio_bytes(), "audio/wav")},
        data={"name": "Narrator", "language": "English", "reference_transcript": "Hello." , "consent_confirmed": "true"},
    ).json()


def test_fake_generation_playback_download_and_delete(app_client):
    client, app = app_client
    profile = make_profile(client)
    response = client.post("/api/generate", json={"profile_id": profile["id"], "voice": "profile", "quality": "fast", "text": "Hello from the local studio."})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["chunk_count"] >= 1
    assert client.get(f"{result['audio_url']}?token={app.state.token}").headers["content-type"].startswith("audio/wav")
    assert client.get(f"{result['download_url']}?token={app.state.token}").status_code == 200
    assert client.delete(f"/api/outputs/{result['id']}").status_code == 200


def test_output_urls_accept_exactly_one_query_token(app_client):
    client, app = app_client
    profile = make_profile(client)
    result = client.post(
        "/api/generate",
        json={"profile_id": profile["id"], "voice": "profile", "quality": "fast", "text": "History playback URL check."},
    ).json()
    response = client.get(f"{result['audio_url']}?token={app.state.token}&t=1")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")


def test_fixed_choices_do_not_require_profiles(app_client):
    client, _ = app_client
    response = client.post("/api/generate", json={"voice": "david", "text": "Hello."})
    assert response.status_code == 200, response.text
    assert response.json()["profile_id"] == "fixed:david-attenborough"


def test_voice_choices_route_to_the_declared_models(app_client):
    client, _ = app_client
    profile = make_profile(client)
    cases = (
        ("david", "fast", None, "david", "best", "fixed:david-attenborough"),
        ("egirl", "fast", None, "egirl-fast", "fast", "fixed:egirl-rvc"),
        ("egirl", "best", None, "egirl-best", "best", "fixed:egirl-rvc"),
        ("profile", "fast", profile["id"], "Qwen/Qwen3-TTS-12Hz-0.6B-Base", "fast", profile["id"]),
        ("profile", "best", profile["id"], "Qwen/Qwen3-TTS-12Hz-1.7B-Base", "best", profile["id"]),
    )
    for voice, quality, profile_id, model_id, expected_quality, output_profile_id in cases:
        response = client.post(
            "/api/generate",
            json={"voice": voice, "quality": quality, "profile_id": profile_id, "text": f"Routing check for {voice}."},
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["model_id"] == model_id
        assert result["quality"] == expected_quality
        assert result["profile_id"] == output_profile_id


def test_qwen_engine_names_are_not_accepted_as_voices(app_client):
    client, _ = app_client
    for old_voice in ("qwen-fast", "qwen-best"):
        response = client.post("/api/generate", json={"voice": old_voice, "text": "No engine names as voices."})
        assert response.status_code == 422
