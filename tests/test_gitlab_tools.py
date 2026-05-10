"""Tests for vixcode.gitlab_tools — mocked GitLab REST client."""
from unittest.mock import MagicMock, patch

import pytest
import requests

from vixcode import gitlab_tools as gl


@pytest.fixture(autouse=True)
def reset_gl_client():
    gl.reset_client()
    yield
    gl.reset_client()


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv("GITLAB_TOKEN", "test-token")
    monkeypatch.setenv("GITLAB_URL", "https://gl.example.com")
    monkeypatch.setenv("GITLAB_PROJECT", "team/svc")


def _ok(payload, status: int = 200):
    """Build a MagicMock that mimics a successful requests.Response."""
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload
    resp.text = "ok"
    resp.content = b"ok"
    return resp


def _err(status: int, text: str = "boom"):
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    resp.content = text.encode()
    return resp


# ── Configuration -----------------------------------------------------------

class TestEnabledFlag:
    def test_disabled_when_no_token(self, monkeypatch):
        monkeypatch.delenv("GITLAB_TOKEN", raising=False)
        assert gl.is_gitlab_enabled() is False

    def test_enabled_when_token_set(self, monkeypatch):
        monkeypatch.setenv("GITLAB_TOKEN", "x")
        assert gl.is_gitlab_enabled() is True


class TestRemoteParsing:
    @pytest.mark.parametrize("url,expected", [
        ("https://gitlab.com/group/repo.git",        "group/repo"),
        ("https://gitlab.com/group/sub/repo.git",    "group/sub/repo"),
        ("git@gitlab.com:group/repo.git",            "group/repo"),
        ("git@gitlab.com:group/sub/repo.git",        "group/sub/repo"),
        ("https://gitlab.example.com/team/svc",      "team/svc"),
    ])
    def test_parses_known_formats(self, url, expected):
        proc = MagicMock(returncode=0, stdout=url + "\n")
        with patch("vixcode.gitlab_tools.subprocess.run", return_value=proc):
            assert gl._detect_project_from_git() == expected

    def test_returns_none_when_no_remote(self):
        with patch("vixcode.gitlab_tools.subprocess.run",
                   return_value=MagicMock(returncode=128, stdout="")):
            assert gl._detect_project_from_git() is None


# ── Client construction -----------------------------------------------------

class TestClientInit:
    def test_raises_without_token(self, monkeypatch):
        monkeypatch.delenv("GITLAB_TOKEN", raising=False)
        with pytest.raises(gl.GitLabError, match="GITLAB_TOKEN"):
            gl.GitLabClient()

    def test_raises_without_project(self, monkeypatch):
        monkeypatch.setenv("GITLAB_TOKEN", "t")
        monkeypatch.delenv("GITLAB_PROJECT", raising=False)
        with patch("vixcode.gitlab_tools._detect_project_from_git", return_value=None):
            with pytest.raises(gl.GitLabError, match="GITLAB_PROJECT"):
                gl.GitLabClient()

    def test_url_encodes_project_path(self, env):
        c = gl.GitLabClient()
        assert c._project_enc == "team%2Fsvc"
        assert c._proj("/issues") == "/projects/team%2Fsvc/issues"


# ── HTTP error handling -----------------------------------------------------

class TestHTTPErrors:
    @patch("vixcode.gitlab_tools.requests.request")
    def test_400_raises_gitlab_error(self, req, env):
        req.return_value = _err(404, "not found")
        with pytest.raises(gl.GitLabError, match="404"):
            gl.GitLabClient().get("/projects/x/issues")

    @patch("vixcode.gitlab_tools.requests.request",
           side_effect=requests.ConnectionError("dns"))
    def test_network_error_raises_gitlab_error(self, _req, env):
        with pytest.raises(gl.GitLabError, match="network error"):
            gl.GitLabClient().get("/projects/x/issues")


# ── Tool happy paths --------------------------------------------------------

class TestIssueTools:
    @patch("vixcode.gitlab_tools.requests.request")
    def test_list_issues_summarizes(self, req, env):
        req.return_value = _ok([
            {"iid": 1, "state": "opened", "title": "Login broken",
             "author": {"username": "alice"}, "labels": ["bug"]},
            {"iid": 2, "state": "opened", "title": "Add docs",
             "author": {"username": "bob"}, "labels": []},
        ])
        out = gl.gitlab_list_issues()
        assert "#1" in out and "Login broken" in out
        assert "#2" in out and "Add docs" in out
        # Auth header propagated
        assert req.call_args.kwargs["headers"]["PRIVATE-TOKEN"] == "test-token"

    @patch("vixcode.gitlab_tools.requests.request")
    def test_get_issue_includes_comments(self, req, env):
        req.side_effect = [
            _ok({"iid": 7, "state": "opened", "title": "X",
                 "author": {"username": "alice"}, "labels": [],
                 "description": "long desc", "web_url": "https://gl/x/-/issues/7"}),
            _ok([{"author": {"username": "bob"}, "body": "looking into it"}]),
        ]
        out = gl.gitlab_get_issue(7)
        assert "#7" in out and "long desc" in out
        assert "looking into it" in out

    @patch("vixcode.gitlab_tools.requests.request")
    def test_create_issue_returns_url(self, req, env):
        req.return_value = _ok({"iid": 99, "web_url": "https://gl/x/-/issues/99"})
        assert gl.gitlab_create_issue("title").startswith("Created issue #99")

    @patch("vixcode.gitlab_tools.requests.request")
    def test_comment_issue(self, req, env):
        req.return_value = _ok({"id": 42})
        out = gl.gitlab_comment_issue(7, "thanks!")
        assert "Commented on issue #7" in out


class TestMrAndPipelineTools:
    @patch("vixcode.gitlab_tools.requests.request")
    def test_get_mr_with_diff(self, req, env):
        req.side_effect = [
            _ok({"iid": 5, "state": "opened", "title": "T",
                 "source_branch": "feat", "target_branch": "main",
                 "author": {"username": "a"}, "description": "d",
                 "web_url": "https://gl/x/-/mr/5"}),
            _ok([]),  # notes
            _ok({"changes": [{"new_path": "foo.py", "new_file": False}]}),
        ]
        out = gl.gitlab_get_mr(5, include_diff=True)
        assert "!5" in out and "foo.py" in out

    @patch("vixcode.gitlab_tools.requests.request")
    def test_list_pipelines(self, req, env):
        req.return_value = _ok([
            {"id": 1, "status": "failed", "ref": "main",
             "sha": "abcdef0123", "web_url": "u"},
        ])
        out = gl.gitlab_list_pipelines(status="failed")
        assert "failed" in out and "abcdef01" in out

    @patch("vixcode.gitlab_tools.requests.get")
    @patch("vixcode.gitlab_tools.requests.request")
    def test_get_job_log_truncates(self, req, get, env):
        req.return_value = _ok({})  # unused; ensures client init succeeds
        # actual log fetch uses requests.get directly
        log_resp = MagicMock(status_code=200,
                             text="\n".join(f"line {i}" for i in range(500)))
        get.return_value = log_resp
        out = gl.gitlab_get_job_log(123, tail=50)
        assert out.startswith("… (truncated)")
        assert "line 499" in out and "line 0" not in out


# ── Registry sanity ---------------------------------------------------------

class TestRegistry:
    def test_handlers_match_definitions(self):
        names_in_defs = {td["function"]["name"] for td in gl.GITLAB_TOOL_DEFINITIONS}
        names_in_handlers = set(gl.GITLAB_TOOL_HANDLERS.keys())
        assert names_in_defs == names_in_handlers

    def test_every_tool_has_a_default_permission(self):
        names_in_handlers = set(gl.GITLAB_TOOL_HANDLERS.keys())
        names_in_perms = set(gl.GITLAB_DEFAULT_PERMISSIONS.keys())
        assert names_in_handlers == names_in_perms
