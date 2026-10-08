"""REQ-07: acceso de solo lectura al repositorio en GitHub (commits y diffs) y creación de issues autorizados."""
import httpx

from ..config import settings
from ..security import get_secret

API = "https://api.github.com"


class GitHubError(RuntimeError):
    pass


class GitHubClient:
    def __init__(self, repo: str | None = None, branch: str | None = None):
        self.repo = repo or settings.github_repo
        self.branch = branch or settings.github_branch
        if not self.repo or "/" not in self.repo:
            raise GitHubError("GITHUB_REPO debe tener el formato usuario/repositorio")
        self._headers = {
            "Authorization": f"Bearer {get_secret('github_token')}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _req(self, method: str, path: str, **kwargs):
        try:
            r = httpx.request(method, f"{API}{path}", headers=self._headers, timeout=30, **kwargs)
        except httpx.HTTPError as e:
            raise GitHubError(f"Error de red con GitHub: {e}") from e
        if r.status_code >= 400:
            raise GitHubError(f"GitHub {method} {path} -> {r.status_code}: {r.text[:200]}")
        return r.json()

    def recent_commits(self, since_sha: str | None, limit: int = 10) -> list[dict]:
        """Commits de la rama posteriores a since_sha (o los últimos `limit` si no hay referencia)."""
        commits = self._req("GET", f"/repos/{self.repo}/commits",
                            params={"sha": self.branch, "per_page": 50})
        result = []
        for c in commits:
            if since_sha and c["sha"] == since_sha:
                break
            result.append(c)
            if not since_sha and len(result) >= limit:
                break
        return list(reversed(result))  # de más antiguo a más reciente

    def commit_detail(self, sha: str) -> dict:
        return self._req("GET", f"/repos/{self.repo}/commits/{sha}")

    def create_issue(self, title: str, body: str, labels: list[str] | None = None) -> dict:
        payload = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels
        return self._req("POST", f"/repos/{self.repo}/issues", json=payload)
