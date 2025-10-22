# CodeStyle.md — Правила генерации и оформления кода (для LLM и людей)

## Версия языка и общий подход
- **Python: 3.13** (ориентироваться на доступные возможности 3.13).
- **Асинхронный код — по умолчанию**. Все внешние операции (БД, сеть, файловая система, ожидания) — через `async`/`await`. Синхронные вызовы допускаются только внутри `asyncio.to_thread(...)` или при отсутствии асинхронной альтернативы.
- Код должен быть **читаемым**, **типобезопасным** и **минималистичным**: явные соглашения, отсутствие «магии», минимально необходимая абстракция.
- Все импорты должны быть АБСОЛЮТНЫМИ никаких локальных или относительных импортов

## Тайпхинты (обязательно)
- Все **публичные функции/методы** и **поверхностные приватные** — с явными type hints.
- Используем **PEP 604** объединения: `str | None` вместо `Optional[str]` / «дженериков» вида `Optional[...]`.
- Не использовать `Any`, если можно избежать. Предпочтительно:
  - `typing.Self` для методов, возвращающих экземпляр;
  - `typing.Literal`, `typing.TypedDict`, `typing.TypeAlias` — когда это повышает выразительность;
  - `collections.abc` для протоколов контейнеров (например, `Iterable[str]`).
- Возвращаемые типы **всегда** указываем явно.
- Для константных структур — `Final`, для неизменяемых — `tuple`, `frozenset`.

> Исключение: в ORM-моделях SQLAlchemy 2 допускается применение типового контейнера `Mapped[T]` (это требование SQLAlchemy). Во **всех остальных** местах для опциональности используем `T | None`.

## Комментарии и докстринги
- Комментарии и докстринги — **на английском языке**.
- Стиль докстрингов: **reST** со схемой параметров:
  ```python
  def example(field: str | None) -> int:
      """Short descr.
      
      Descr.
      
      :param field: descr field `field`.
      :return: descr return.
      :raises ValueError: when input value not valid.
      """
      ...
  ```
- Не дублировать код в докстрингах; объяснять «зачем» и «что вернётся», а не «что делает каждая строка».

## Структура проекта (соблюдать текущую)
Сохраняем действующую структуру модулей и нейминг. Новые компоненты размещаем согласованно:
- `src/internal/...` — внутренняя логика (оркестраторы, задачи, адаптеры).
- `src/api/...` — FastAPI-эндпоинты, схемы запросов/ответов.
- `src/db/...` — модели ORM, сессии, миграции.
- `src/config/...` — настройки (Pydantic Settings).
- `src/internal/prometheus/...` — метрики/экспортер.

## SQLAlchemy 2.x (обязательно 2 и выше)
- Только декларативный стиль **SQLAlchemy 2+** с **async**-движком.
- Сессии: `async_sessionmaker`, контекстные менеджеры `async with`.
- Типизация полей ORM:
  ```python
  from sqlalchemy.orm import Mapped, mapped_column
  from sqlalchemy import String

  class User(Base):
      __tablename__ = "user"
      id: Mapped[int] = mapped_column(primary_key=True)
      name: Mapped[str] = mapped_column(String(128))
      email: Mapped[str | None] = mapped_column(String(256), unique=True)
  ```
- В сигнатурах функций/методов и DTO использовать `str | None` и др. PEP 604 объединения, **не** `Optional[str]`.
- Запросы — современный 2.0 style (`select(...)`, `scalar_one_or_none()`, `execute()` и т.д.).

## Асинхронность и конкурентность
- Любые I/O — асинхронные API. Для блокирующих операций — `await asyncio.to_thread(fn, ...)`.
- Не блокировать event loop: никаких `time.sleep`, только `asyncio.sleep`.
- Внешние процессы — через `asyncio.create_subprocess_exec`/`shell`.
- Таймауты и отмена задач — явные (`asyncio.timeout`, `task.cancel()`), корректно обрабатывать `CancelledError`.
- Очереди/семафоры — из `asyncio` (или `anyio`) при необходимости.

## Логи, ошибки, метрики
- Логирование — через **loguru**. Уровни: `debug`/`info`/`warning`/`error`/`exception`.
- Исключения не глушить; перехватывать там, где есть понятная стратегия восстановления или требуется конвертация в доменную ошибку.
- Метрики — Prometheus: Counters/Gauges/Histograms, подписи (labels) стабильные и осмысленные.

## Конфигурация и секреты
- Конфигурация — **pydantic-settings** (Pydantic v2). Переменные окружения → Settings-модель.
- **Никаких секретов в коде**. Секреты — через Vault/ENV. Для локала — `.env` (в `.gitignore`).

## API (FastAPI)
- Все эндпоинты — асинхронные. Валидация — Pydantic v2 модели.
- Ответы — явные `response_model` (даже если совпадают с request).
- Депенденси-инъекция для сессий БД, конфигов и сервисов.
- Чёткая семантика HTTP-кодов: 2xx — успех; 4xx — вина клиента; 5xx — наши ошибки.
- Документация — описывать поля и коды ответа. Кратко и по делу.

## Форматирование, линтинг, статанализ
- **ruff** — линтер и форматтер. Включить правила:
  - базовые `E`, `F`, `I` (imports), `UP` (modernize), `ANN` (annotations), `B` (bugbear), `ASYNC`, `RUF`.
- **mypy**/**pyright** — статическая проверка. Настройки строгие для публичных модулей.
- Именование: `snake_case` для функций/переменных, `PascalCase` для классов, `UPPER_SNAKE_CASE` для констант.
- Максимальная ширина строки — 120 символов.

## Тестирование
- `pytest` + `pytest-asyncio` для асинхронных тестов.
- Юнит-тесты на бизнес-логику и контрактные тесты на API.
- Фикстуры для «чистой» БД и временных каталогов.
- Тесты должны запускаться в CI и быть детерминированными.

## Работа LLM при генерации кода
- Всегда:
  - писать код для **Python 3.13**;
  - использовать **type hints везде** (PEP 604 объединения);
  - писать **докстринги на русском** с блоками `:param`, `:return:`, `:raises:`;
  - генерировать **асинхронные** версии API/DAO/клиентов;
  - при работе с SQLAlchemy — синтаксис **2.x**, async-сессии и типизация полей через `Mapped[...]`, а в сигнатурах — `str | None` и т.п.;
  - следовать текущей структуре проекта и неймингу модулей.

## Примеры коротких шаблонов

### Асинхронный DAO-функционал
```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    """Вернуть пользователя по email.

    :param session: Асинхронная сессия БД.
    :param email: Email пользователя.
    :return: Модель пользователя или None.
    """
    stmt = select(User).where(User.email == email)
    res = await session.execute(stmt)
    return res.scalar_one_or_none()
```

### FastAPI endpoint
```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/{user_id}", response_model=UserOut)
async def get_user(user_id: int, session: AsyncSession = Depends(get_session)) -> UserOut:
    """Получить пользователя по id.

    :param user_id: Идентификатор пользователя.
    :param session: Асинхронная сессия БД.
    :return: DTO пользователя.
    :raises HTTPException: 404 если не найден.
    """
    user = await users_dao.get_by_id(session, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserOut.model_validate(user)
```

### Логирование и ошибки
```python
from loguru import logger

async def process_item(item_id: int) -> None:
    """Обработать элемент.

    :param item_id: Идентификатор элемента.
    :raises RuntimeError: При фатальной ошибке обработки.
    """
    logger.info("Начало обработки item_id={}", item_id)
    try:
        ...
    except Exception as exc:  # конкретизировать при возможности
        logger.exception("Ошибка обработки item_id=%s", item_id)
        raise RuntimeError("Processing failed") from exc
```

---

Поддерживайте единый стиль во всех модулях: типизация, асинхронность, русскоязычные докстринги, SQLAlchemy 2.x, Prometheus-метрики, конфиги через pydantic-settings. Если возникает неоднозначность — предпочтение простоте и явности.
