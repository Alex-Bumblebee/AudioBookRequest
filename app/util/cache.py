import time
from abc import ABC
from typing import Optional, overload

from sqlmodel import Session, select

from app.internal.models import Config


class SimpleCache[VT, *KTs]:
    _cache: dict[tuple[*KTs], tuple[int, VT]] = {}

    def get(self, source_ttl: int, *query: *KTs) -> Optional[VT]:
        hit = self._cache.get(query)
        if not hit:
            return None
        cached_at, sources = hit
        if cached_at + source_ttl < time.time():
            return None
        return sources

    def get_all(self, source_ttl: int) -> dict[tuple[*KTs], VT]:
        now = int(time.time())

        return {
            query: sources
            for query, (cached_at, sources) in self._cache.items()
            if cached_at + source_ttl > now
        }

    def set(self, sources: VT, *query: *KTs):
        self._cache[query] = (int(time.time()), sources)

    def flush(self):
        self._cache = {}


class StringConfigCache[L: str](ABC):
    _cache: dict[L, str] = {}

    @overload
    def get(self, session: Session, key: L) -> Optional[str]:
        pass

    @overload
    def get(self, session: Session, key: L, default: str) -> str:
        pass

    def get(
        self, session: Session, key: L, default: Optional[str] = None
    ) -> Optional[str]:
        if key in self._cache:
            return self._cache[key]
        return (
            session.exec(select(Config.value).where(Config.key == key)).one_or_none()
            or default
        )

    def set(self, session: Session, key: L, value: str):
        old = session.exec(select(Config).where(Config.key == key)).one_or_none()
        if old:
            old.value = value
        else:
            old = Config(key=key, value=value)
        session.add(old)
        session.commit()
        self._cache[key] = value

    def delete(self, session: Session, key: L):
        old = session.exec(select(Config).where(Config.key == key)).one_or_none()
        if old:
            session.delete(old)
            session.commit()
        if key in self._cache:
            del self._cache[key]

    @overload
    def get_int(self, session: Session, key: L) -> Optional[int]:
        pass

    @overload
    def get_int(self, session: Session, key: L, default: int) -> int:
        pass

    def get_int(
        self, session: Session, key: L, default: Optional[int] = None
    ) -> Optional[int]:
        val = self.get(session, key)
        if val:
            return int(val)
        return default

    def set_int(self, session: Session, key: L, value: int):
        self.set(session, key, str(value))

    def get_bool(self, session: Session, key: L) -> Optional[bool]:
        try:
            val = self.get_int(session, key)
        except ValueError:  # incase if the db has an old bool string instead of an int
            return False
        if val is not None:
            return val != 0
        return None

    def set_bool(self, session: Session, key: L, value: bool):
        self.set_int(session, key, int(value))
