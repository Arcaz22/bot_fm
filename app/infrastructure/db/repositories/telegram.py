from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.telegram.entities import TelegramUser
from app.domain.telegram.ports import TelegramUserRepo
from app.infrastructure.db.models import SysTelegramUser

class SqlTelegramUserRepo(TelegramUserRepo):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, telegram_id: int) -> TelegramUser | None:
        # GANTI: self.s.get -> await self.session.get
        orm = await self.session.get(SysTelegramUser, telegram_id)

        if not orm:
            return None

        return TelegramUser(
            id=orm.id,
            first_name=orm.first_name,
            username=orm.username,
            # Pastikan field ini ada di Entity dan Model Anda
            current_state=orm.current_state,
            temp_data=orm.temp_data,
            # is_active=orm.is_active,
            # last_interaction_at=orm.last_interaction_at,
        )

    async def upsert(self, user: TelegramUser) -> TelegramUser:
        # GANTI: Logic 'or' one-liner susah di async, pecah jadi if/else
        orm = await self.session.get(SysTelegramUser, user.id)

        if not orm:
            # Create Baru
            orm = SysTelegramUser(id=user.id)
            self.session.add(orm) # .add() itu sync (memory only), jadi gak perlu await

        # Update Field
        orm.first_name = user.first_name
        orm.username = user.username
        orm.current_state = user.current_state
        orm.temp_data = user.temp_data
        # orm.is_active = user.is_active

        # GANTI: flush dan commit wajib await
        await self.session.flush()
        await self.session.commit()

        return user

    async def update_state(self, telegram_id: int, state: str, temp_data: dict) -> None:
        # GANTI: self.s.query(...).update(...) TIDAK BISA DI ASYNC
        # Gunakan 'update' statement dari sqlalchemy core
        stmt = (
            update(SysTelegramUser)
            .where(SysTelegramUser.id == telegram_id)
            .values(current_state=state, temp_data=temp_data)
        )

        await self.session.execute(stmt)
        await self.session.commit()
