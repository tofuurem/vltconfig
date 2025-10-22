# vault-pydantic-simple

> **📁 Project Documentation Location**
> All project documentation, improvements, and task tracking is located in `.claude/docs/`:
> - **IMPROVEMENTS.md** - Detailed analysis and improvement recommendations
> - **TASKS.md** - Step-by-step implementation tasks
> - **CODESTYLE.md** - General code style guide (with project-specific exceptions)

## Обзор проекта

**vault-pydantic-simple** - это Python библиотека для удобного получения конфигурации из HashiCorp Vault KV хранилища и JSON файлов с валидацией через pydantic.

### Основные характеристики
- **Название пакета**: vault-pydantic-simple
- **Версия**: 0.5.0
- **Автор**: tofuurem (rabbit_1399@icloud.com)
- **Лицензия**: MIT
- **Python версии**: >= 3.11 (поддержка 3.11, 3.12, 3.13)
- **PyPI**: https://pypi.org/p/vault-pydantic-simple

## Архитектура

### Основные компоненты

Проект построен на модульной архитектуре с использованием пользовательских источников настроек (custom settings sources) из pydantic-settings.

```
vlt/
├── __init__.py           # Экспортирует VaultJsonConfig
├── config.py             # Модель VaultAccess для аутентификации
├── constants.py          # Константы проекта
├── json_source.py        # Источник настроек из JSON
└── vault_source.py       # Источник настроек из Vault
```

### Приоритет источников конфигурации

Конфигурация загружается в следующем порядке приоритета (vlt/__init__.py:25-32):

1. **Environment variables** (высший приоритет)
2. **Vault KV store** (`PydanticVaultSource`)
3. **JSON file** (`PydanticJSONSource`)
4. **Init settings** (параметры конструктора)
5. **Dotenv settings** (.env файл)
6. **File secret settings** (файлы секретов)

## Ключевые компоненты

### 1. VaultJsonConfig (vlt/__init__.py)

Базовый класс для создания конфигурационных моделей приложения.

**Функциональность:**
- Наследуется от `pydantic_settings.BaseSettings`
- Переопределяет метод `settings_customise_sources` для добавления пользовательских источников
- Использует `populate_by_name=True` для поддержки алиасов полей

**Пример использования:**
```python
from vlt import VaultJsonConfig

class Configuration(VaultJsonConfig):
    value: str
    database_url: str
    api_key: str
```

### 2. VaultAccess (vlt/config.py)

Модель для настройки подключения к HashiCorp Vault.

**Поля конфигурации:**
- `address` (VAULT_ADDRESS) - URL адрес Vault сервера
- `token` (VAULT_TOKEN) - Токен для аутентификации (опционально)
- `username` (VAULT_USERNAME) - Имя пользователя для userpass auth (опционально)
- `password` (VAULT_PASSWORD) - Пароль для userpass auth (опционально)
- `app_name` (VAULT_APP_NAME) - Имя приложения/путь в Vault KV
- `mount_point` (VAULT_MOUNT_POINT) - Mount point для KV engine (по умолчанию: "secret")

**Валидация:**
- Проверяет наличие либо токена, либо пары username+password
- Использует pydantic model_validator для проверки учетных данных

### 3. PydanticVaultSource (vlt/vault_source.py)

Пользовательский источник настроек для получения конфигурации из Vault.

**Функциональность:**
- Поддерживает два метода аутентификации:
  - Token-based authentication
  - Username/Password authentication (userpass)
- Подключается к Vault KV v2 API
- Извлекает данные из `secret["data"]["data"]`

**Алгоритм работы (_auth_by_userpass):**
```python
if cfg.token:
    # Прямая аутентификация по токену
    client = hvac.Client(url=cfg.address, token=cfg.token)
else:
    # Аутентификация через userpass
    client = hvac.Client(url=cfg.address)
    resp = client.auth.userpass.login(username=cfg.username, password=cfg.password)
    client.token = resp["auth"]["client_token"]
```

**Обработка ошибок:**
- Логирует исключения через loguru
- Возвращает пустой словарь при ошибке, позволяя использовать другие источники

### 4. PydanticJSONSource (vlt/json_source.py)

Пользовательский источник настроек для получения конфигурации из JSON файла.

**Функциональность:**
- Ищет файл `config.json` по пути из переменной окружения `PYDANTIC_JSON_PATH`
- Если переменная не задана, ищет в директории пакета
- Парсит JSON и возвращает данные как словарь

**Путь к файлу:**
```python
path_env = os.getenv(PYDANTIC_JSON_PATH, default=None)
config_path = Path(path_env or os.path.dirname(__file__), "config.json")
```

**Обработка ошибок:**
- Логирует предупреждения при отсутствии файла
- Позволяет приложению работать без config.json

## Конфигурация

### Переменные окружения

#### Обязательные:
- `VAULT_ADDRESS` - адрес Vault сервера (например: https://vault.example.com)
- `VAULT_APP_NAME` - путь к секретам в Vault KV

#### Аутентификация (одно из):
- `VAULT_TOKEN` - токен доступа
- `VAULT_USERNAME` + `VAULT_PASSWORD` - учетные данные userpass

#### Опциональные:
- `VAULT_MOUNT_POINT` - mount point KV engine (по умолчанию: "secret")
- `PYDANTIC_JSON_PATH` - путь к директории с config.json

## Примеры использования

### Базовый пример (dev/cfg_try.py)

```python
import os
from vlt import VaultJsonConfig

class Configuration(VaultJsonConfig):
    value: str

# Настройка через переменные окружения
os.environ["VAULT_ADDRESS"] = "https://vault.b2baisolutions.io"
os.environ["VAULT_USERNAME"] = "readonly"
os.environ["VAULT_PASSWORD"] = "jPQykKGKkWBXigtU0zPvkRXltrEccm"
os.environ["VAULT_APP_NAME"] = "test"
os.environ["VAULT_MOUNT_POINT"] = "vpn"

# Создание конфигурации
config = Configuration()
print(config.value)
```

### Расширенный пример с несколькими полями

```python
from vlt import VaultJsonConfig
from pydantic import Field

class AppConfig(VaultJsonConfig):
    database_url: str = Field(alias="DATABASE_URL")
    api_key: str = Field(alias="API_KEY")
    debug: bool = False
    max_connections: int = 10

# Конфигурация автоматически загружается из:
# 1. Environment variables
# 2. Vault KV store
# 3. config.json
# 4. Значения по умолчанию
config = AppConfig()
```

### Использование с токеном

```python
import os
os.environ["VAULT_ADDRESS"] = "https://vault.example.com"
os.environ["VAULT_TOKEN"] = "s.your-vault-token"
os.environ["VAULT_APP_NAME"] = "myapp/config"

config = AppConfig()
```

### Использование с JSON файлом

```python
import os
os.environ["PYDANTIC_JSON_PATH"] = "/path/to/config/directory"

# Файл /path/to/config/directory/config.json:
# {
#   "database_url": "postgresql://localhost/mydb",
#   "api_key": "test-key",
#   "debug": true
# }

config = AppConfig()
```

## Зависимости

### Основные (pyproject.toml:19-24):
- `hvac>=2.3.0` - клиент для HashiCorp Vault
- `loguru>=0.7.3` - логирование
- `pydantic>=2.10.6` - валидация данных
- `pydantic-settings>=2.7.1` - расширение для настроек

### Разработка (pyproject.toml:34-38):
- `isort>=6.0.0` - сортировка импортов
- `mypy>=1.14.1` - статическая типизация
- `ruff>=0.9.4` - линтер и форматтер

## Разработка

### Установка для разработки

```bash
# Клонирование репозитория
git clone <repository-url>
cd vault-config

# Установка зависимостей (с использованием uv)
uv sync

# Установка dev зависимостей
uv sync --group dev
```

### Инструменты разработки

```bash
# Линтинг с ruff
ruff check .

# Форматирование
ruff format .

# Проверка типов с mypy
mypy vlt/

# Сортировка импортов
isort vlt/
```

### Сборка пакета

```bash
pip install build
python -m build
```

## CI/CD

### GitHub Actions (.github/workflows/main.yml)

**Workflow**: Release
**Триггер**: workflow_dispatch (ручной запуск)

**Этапы:**
1. Установка зависимостей для сборки (`pip install build`)
2. Checkout кода
3. Сборка пакета (`python -m build`)
4. Публикация в PyPI (с использованием trusted publishing)

**Environment:**
- name: pypi
- url: https://pypi.org/p/vault-pydantic-simple
- permissions: id-token: write (для OIDC аутентификации)

## Структура файлов

```
vault-config/
├── .github/
│   └── workflows/
│       └── main.yml          # CI/CD для публикации в PyPI
├── dev/
│   ├── __init__.py
│   └── cfg_try.py            # Пример использования
├── vlt/                      # Основной пакет
│   ├── __init__.py          # Экспорт VaultJsonConfig
│   ├── config.py            # VaultAccess модель
│   ├── constants.py         # Константы (PYDANTIC_JSON_PATH)
│   ├── json_source.py       # JSON источник настроек
│   └── vault_source.py      # Vault источник настроек
├── .gitignore               # Игнорируемые файлы
├── .python-version          # Версия Python для проекта
├── pyproject.toml           # Конфигурация проекта и зависимости
├── README.md                # Документация
└── uv.lock                  # Lock file для uv package manager
```

## Технические детали

### Механизм работы custom settings sources

1. **Инициализация**: При создании экземпляра `VaultJsonConfig`, pydantic-settings вызывает `settings_customise_sources`
2. **Источники**: Каждый источник реализует `PydanticBaseSettingsSource`
3. **Вызов**: pydantic вызывает `__call__()` метод каждого источника
4. **Приоритет**: Значения берутся из первого источника, где они найдены
5. **Объединение**: Результаты объединяются согласно порядку приоритета

### Обработка ошибок

- **Vault ошибки**: Логируются через loguru.error, возвращается пустой dict
- **JSON ошибки**: Логируются через loguru.warning, возвращается пустой dict
- **Валидация**: При отсутствии обязательных credentials выбрасывается ValidationError

### Безопасность

- Поддержка аутентификации через токены (предпочтительно)
- Поддержка userpass для legacy систем
- Не хранит credentials в коде
- Использует переменные окружения для конфигурации

## Возможные улучшения

1. **Кэширование**: Добавить кэширование секретов из Vault
2. **Retry логика**: Реализовать повторные попытки при временных сбоях
3. **Мультиплексные пути**: Поддержка загрузки из нескольких путей в Vault
4. **AppRole auth**: Добавить поддержку AppRole аутентификации
5. **Тесты**: Добавить unit и integration тесты
6. **TTL обработка**: Автоматическое обновление токенов при истечении
7. **Async поддержка**: Асинхронные версии source классов

## История изменений (из git commits)

- `7127c5e` - feat: added mount_point
- `6b8b87b` - fix: bug with import
- `7e002eb` - refactor: clearing project
- `d07db93` - fix: name
- `1738a38` - feat: update ci

## Типичные сценарии использования

### 1. Микросервисная архитектура
```python
# Каждый сервис получает свою конфигурацию из Vault
os.environ["VAULT_APP_NAME"] = "services/user-service"
config = ServiceConfig()
```

### 2. Разработка vs Production
```python
# Development: использует config.json
os.environ["PYDANTIC_JSON_PATH"] = "./config/dev"

# Production: использует Vault
os.environ["VAULT_ADDRESS"] = "https://vault.prod.example.com"
os.environ["VAULT_TOKEN"] = os.environ.get("VAULT_TOKEN_FROM_K8S")
```

### 3. Multi-environment
```python
env = os.getenv("ENV", "dev")
os.environ["VAULT_APP_NAME"] = f"myapp/{env}"
config = AppConfig()
```

## Отладка

### Включение логирования

```python
from loguru import logger

# Настройка уровня логирования
logger.add("vault_config.log", level="DEBUG")

config = AppConfig()
```

### Проверка источника значения

```python
# pydantic позволяет отследить источник каждого поля
config = AppConfig()
print(config.model_dump())
```

## Правила разработки для LLM и разработчиков

### ⚠️ Project-Specific Rules (Отличия от CODESTYLE.md)

**ВАЖНО**: Этот проект имеет **специфические отличия** от общего `.claude/docs/CODESTYLE.md`:

#### Что ОТЛИЧАЕТСЯ от стандартного CODESTYLE.md:

1. **НЕ асинхронный код** ❌
   - `pydantic` и `pydantic-settings` полностью синхронные
   - `hvac` клиент работает синхронно
   - Асинхронная версия технически невозможна

2. **Докстринги на АНГЛИЙСКОМ** 🇬🇧
   - Все docstrings на английском языке
   - Комментарии также на английском
   - Это публичная библиотека на PyPI

3. **Нет SQLAlchemy**
   - Проект не использует БД
   - Не применимы правила для ORM

#### Что СОХРАНЯЕТСЯ из CODESTYLE.md:

- ✅ **Python 3.13** - используем возможности последней версии
- ✅ **Полная типизация** - type hints везде, PEP 604 объединения (`str | None`)
- ✅ **Абсолютные импорты** - никаких относительных импортов
- ✅ **Логирование через loguru** - структурированное логирование
- ✅ **Pydantic v2** - для валидации и настроек
- ✅ **Ruff + mypy** - обязательная проверка кода

### Основные принципы проекта

- **Python 3.11+** - поддержка 3.11, 3.12, 3.13
- **Синхронный код** - pydantic работает синхронно
- **Полная типизация** - type hints везде, без `Any`
- **English docstrings** - все комментарии и документация на английском
- **Абсолютные импорты** - никаких относительных импортов
- **Логирование через loguru** - `trace` для деталей, `info/error` для результатов
- **Pydantic v2** - для валидации и настроек
- **Ruff + mypy** - обязательная проверка кода

Пример правильного кода для этого проекта:
```python
import hvac
from loguru import logger
from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings

class VaultAccess(BaseSettings):
    """Vault connection configuration.

    Supports multiple authentication methods:
    - Token-based (VAULT_TOKEN)
    - Username/Password (VAULT_USERNAME + VAULT_PASSWORD)
    - AppRole (VAULT_ROLE_ID + VAULT_SECRET_ID)
    """

    address: HttpUrl = Field(
        alias="VAULT_ADDRESS",
        description="URL of the Vault server"
    )
    token: str | None = Field(default=None, alias="VAULT_TOKEN")
    app_name: str = Field(alias="VAULT_APP_NAME")

def get_vault_secrets(cfg: VaultAccess) -> dict[str, str | int | float | bool]:
    """Retrieve secrets from Vault.

    :param cfg: Vault configuration with credentials
    :return: Dictionary of secret key-value pairs
    :raises ValueError: If authentication fails or path not found
    """
    logger.trace("Connecting to Vault: {}", cfg.address)

    client = hvac.Client(url=str(cfg.address), token=cfg.token)

    if not client.is_authenticated():
        raise ValueError("Failed to authenticate with Vault")

    logger.trace("Fetching secrets for: {}", cfg.app_name)

    try:
        secret = client.secrets.kv.v2.read_secret_version(path=cfg.app_name)
        data = secret["data"]["data"]
        logger.info("Successfully loaded {} secrets", len(data))
        return data
    except hvac.exceptions.InvalidPath as ex:
        logger.error("Path not found: {}", cfg.app_name)
        raise ValueError(f"Path {cfg.app_name} not found in Vault") from ex
```

### Использование MCP Context7

**ОБЯЗАТЕЛЬНО**: Для понимания API используемых библиотек необходимо использовать **MCP context7**.

Context7 предоставляет актуальную документацию и примеры использования библиотек:
- `hvac` - работа с HashiCorp Vault API
- `pydantic` и `pydantic-settings` - валидация и конфигурация
- `sqlalchemy` - ORM запросы и модели
- `fastapi` - создание REST API
- `loguru` - логирование

**Когда использовать Context7:**
- При добавлении новой функциональности из библиотеки
- При работе с незнакомым API
- Для проверки актуальных best practices
- При обновлении версий зависимостей
- Для понимания асинхронных интерфейсов

**Примеры использования:**
```
# Узнать как работать с Vault KV v2 API
@context7 hvac secrets kv v2

# Посмотреть документацию pydantic-settings
@context7 pydantic-settings custom sources

# Изучить SQLAlchemy 2.x async
@context7 sqlalchemy async session
```

### Workflow разработки

1. **Перед началом работы**:
   - Прочитать `.claude/docs/CODESTYLE.md`
   - Использовать context7 для изучения API нужных библиотек

2. **Во время разработки**:
   - Писать асинхронный код с полной типизацией
   - Документировать на русском языке
   - Следовать структуре проекта

3. **Проверка кода**:
   ```bash
   ruff check .
   ruff format .
   mypy vlt/
   isort vlt/
   ```

4. **Перед коммитом**:
   - Убедиться что все типы указаны
   - Проверить наличие докстрингов
   - Запустить линтеры и тесты

## Контакты и поддержка

- **GitHub Issues**: Для сообщений об ошибках и запросов функций
- **Email**: rabbit_1399@icloud.com
- **PyPI**: https://pypi.org/p/vault-pydantic-simple
