from pathlib import Path


def test_security_patched_image_and_environment_dependencies_are_pinned():
    requirements = (Path(__file__).parents[1] / "requirements.txt").read_text()
    assert "pillow==13.0.0" in requirements
    assert "python-dotenv==1.2.2" in requirements
    assert "pillow==11.0.0" not in requirements
    assert "python-dotenv==1.0.0" not in requirements
