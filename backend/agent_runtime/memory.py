from typing import Any, Dict, List, Optional

from .models import UserMemory


class UserMemoryStore:
    """Small persistence wrapper for user-scoped agent memory."""

    def __init__(self, *, user):
        self.user = user

    def remember(
        self,
        *,
        memory_type: str,
        memory_key: str,
        memory_value: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> UserMemory:
        memory, _ = UserMemory.objects.update_or_create(
            user=self.user,
            memory_type=memory_type,
            memory_key=memory_key,
            defaults={
                'memory_value': memory_value,
                'metadata': metadata or {},
            },
        )
        return memory

    def recall(self, *, memory_type: str, memory_key: str) -> Optional[Dict[str, Any]]:
        try:
            memory = UserMemory.objects.get(
                user=self.user,
                memory_type=memory_type,
                memory_key=memory_key,
            )
        except UserMemory.DoesNotExist:
            return None
        return {
            'memory_type': memory.memory_type,
            'memory_key': memory.memory_key,
            'memory_value': memory.memory_value,
            'metadata': memory.metadata,
            'updated_at': memory.updated_at.isoformat(),
        }

    def list_memories(
        self,
        *,
        memory_type: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        queryset = UserMemory.objects.filter(user=self.user)
        if memory_type:
            queryset = queryset.filter(memory_type=memory_type)

        items = []
        for memory in queryset.order_by('-updated_at')[:limit]:
            items.append({
                'memory_type': memory.memory_type,
                'memory_key': memory.memory_key,
                'memory_value': memory.memory_value,
                'metadata': memory.metadata,
                'updated_at': memory.updated_at.isoformat(),
            })
        return items

    def forget(self, *, memory_type: str, memory_key: str) -> int:
        deleted, _ = UserMemory.objects.filter(
            user=self.user,
            memory_type=memory_type,
            memory_key=memory_key,
        ).delete()
        return deleted
