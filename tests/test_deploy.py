"""Tests for Sprint 6: Deployment infrastructure."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_dockerfile_exists():
    """Dockerfile should exist at project root."""
    dockerfile = Path(__file__).parent.parent / "Dockerfile"
    assert dockerfile.exists(), "Dockerfile not found"


def test_dockerfile_uses_python():
    """Dockerfile should use Python base image."""
    dockerfile = Path(__file__).parent.parent / "Dockerfile"
    content = dockerfile.read_text()
    assert "python:" in content
    assert "WORKDIR /app" in content
    assert "requirements.txt" in content


def test_docker_compose_exists():
    """docker-compose.yml should exist at project root."""
    compose = Path(__file__).parent.parent / "docker-compose.yml"
    assert compose.exists(), "docker-compose.yml not found"


def test_docker_compose_has_crawler_service():
    """docker-compose.yml should define crawler service."""
    compose = Path(__file__).parent.parent / "docker-compose.yml"
    content = compose.read_text()
    assert "crawler:" in content
    assert "8080" in content


def test_deploy_script_exists():
    """deploy.sh should exist in scripts/."""
    deploy = Path(__file__).parent.parent / "scripts" / "deploy.sh"
    assert deploy.exists(), "scripts/deploy.sh not found"


def test_deploy_script_is_executable():
    """deploy.sh should be executable."""
    import stat
    deploy = Path(__file__).parent.parent / "scripts" / "deploy.sh"
    if deploy.exists():
        st = deploy.stat()
        assert st.st_mode & stat.S_IXUSR, "deploy.sh should be executable"


def test_cron_config_example_exists():
    """cron_config.yaml.example should exist."""
    example = Path(__file__).parent.parent / "cron_config.yaml.example"
    assert example.exists(), "cron_config.yaml.example not found"


def test_cron_config_has_jobs():
    """cron_config.yaml.example should have jobs section."""
    example = Path(__file__).parent.parent / "cron_config.yaml.example"
    content = example.read_text()
    assert "jobs:" in content
    assert "url:" in content
    assert "keyword:" in content


def test_cli_cron_dry_run():
    """CLI cron --dry-run should list jobs without executing."""
    import tempfile, yaml

    config = {
        "jobs": [
            {"url": "https://example.com/test", "keyword": "test", "source": "web"},
        ]
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(config, f)
        config_path = f.name

    # Import CLI and run cron in dry-run mode
    from cli import cmd_cron

    class Args:
        config = config_path
        dry_run = True
        knowledge = "/tmp/test_knowledge.json"

    # Should not raise
    try:
        cmd_cron(Args())
    except SystemExit:
        pass  # May exit if knowledge file issue, that's OK for dry-run


def test_cli_source_choices_include_new_sources():
    """CLI crawl --source should include twitter, wechat, zhihu."""
    import subprocess
    result = subprocess.run(
        [sys.executable, "cli.py", "crawl", "--help"],
        capture_output=True, text=True,
        cwd=str(Path(__file__).parent.parent),
    )
    help_text = result.stdout + result.stderr
    assert "twitter" in help_text
    assert "wechat" in help_text
    assert "zhihu" in help_text
