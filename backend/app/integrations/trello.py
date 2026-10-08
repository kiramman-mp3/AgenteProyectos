"""REQ-03: cliente de la API REST de Trello (lectura del tablero y modificaciones autorizadas)."""
import httpx

from ..config import settings
from ..security import get_secret

API = "https://api.trello.com/1"

PRIORITY_COLORS = {0: "red", 1: "orange", 2: "green"}


class TrelloError(RuntimeError):
    pass


class TrelloClient:
    def __init__(self, board_id: str | None = None):
        self.board_id = board_id or settings.trello_board_id
        if not self.board_id:
            raise TrelloError("TRELLO_BOARD_ID no está configurado")
        self._auth = {"key": get_secret("trello_api_key"), "token": get_secret("trello_token")}

    def _req(self, method: str, path: str, **params):
        try:
            r = httpx.request(method, f"{API}{path}", params={**self._auth, **params}, timeout=30)
        except httpx.HTTPError as e:
            raise TrelloError(f"Error de red con Trello: {e}") from e
        if r.status_code >= 400:
            raise TrelloError(f"Trello {method} {path} -> {r.status_code}: {r.text[:200]}")
        return r.json()

    # ---------- Lectura ----------

    def fetch_board(self) -> dict:
        """Devuelve tablero, listas, miembros, etiquetas y tarjetas abiertas (con checklists)."""
        board = self._req("GET", f"/boards/{self.board_id}", fields="name,url,desc")
        lists = self._req("GET", f"/boards/{self.board_id}/lists", filter="open", fields="name,pos")
        members = self._req("GET", f"/boards/{self.board_id}/members", fields="fullName,username")
        labels = self._req("GET", f"/boards/{self.board_id}/labels", fields="name,color", limit=1000)
        cards = self._req(
            "GET", f"/boards/{self.board_id}/cards/open",
            fields="name,desc,due,start,dueComplete,idList,idMembers,idLabels,labels,shortLink,url,"
                   "dateLastActivity,pos",
            checklists="all",
            checklist_fields="name",
        )
        # Las tarjetas de listas archivadas siguen "abiertas" en la API: se excluyen.
        open_lists = {lst["id"] for lst in lists}
        cards = [c for c in cards if c["idList"] in open_lists]
        return {"board": board, "lists": lists, "members": members, "labels": labels, "cards": cards}

    # ---------- Escritura (solo invocada por el ejecutor de acciones autorizadas) ----------

    def update_card(self, card_id: str, **fields) -> dict:
        return self._req("PUT", f"/cards/{card_id}", **fields)

    def add_comment(self, card_id: str, text: str) -> dict:
        return self._req("POST", f"/cards/{card_id}/actions/comments", text=text)

    def ensure_label(self, name: str, color: str | None = None) -> str:
        for lb in self._req("GET", f"/boards/{self.board_id}/labels", fields="name,color", limit=1000):
            if (lb.get("name") or "").strip().lower() == name.lower():
                return lb["id"]
        created = self._req("POST", "/labels", name=name, color=color or "blue", idBoard=self.board_id)
        return created["id"]
