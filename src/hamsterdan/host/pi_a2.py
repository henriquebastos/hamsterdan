"""Host-owned policy and authority boundaries for Petrus Pi native A2 Local."""

from __future__ import annotations

import os
import stat
import tempfile
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from petrus.agenticus.connection.custody import ConnectionIdentity
from petrus.agenticus.connection.key import KeyContext, KeyErasureEvidence, KeyOperationError
from petrus.agenticus.hands.contract import ToolMethod
from petrus.agenticus.runtime.pi import PI_API_KEY_CATALOG
from petrus.agenticus.runtime.pi_a2_host import (
    PiA2DirectAuthority,
    PiA2RuntimeHost,
    PiA2RuntimeHostConfig,
    compose_pi_a2_runtime,
)

from .agenticus import PI_MODEL, PI_PROVIDER

_KEY_VERSION = b"\x01"
_KEY_BYTES = 32
_NONCE_BYTES = 12
_MAX_API_KEY_BYTES = 512
_CONNECTION_ID = "hamsterdan-pi-a2-direct-v1"
_ACCOUNT_FINGERPRINT = "hamsterdan-direct-authority-v1"
_CAPABILITIES = frozenset({ToolMethod.WORKSPACE_READ, ToolMethod.WORKSPACE_SEARCH, ToolMethod.WORKSPACE_WRITE})


@dataclass(frozen=True)
class PiA2InstallationConfig:
    """Installation-owned runtime paths and redacted direct authority."""

    provider: str
    model: str
    direct_key: str = field(repr=False)
    cli_path: Path
    node_path: Path
    package_root: Path

    def __post_init__(self) -> None:
        if (self.provider, self.model) not in PI_API_KEY_CATALOG:
            raise ValueError("Agenticus requires an exact qualified Pi provider/model pair")
        if not 16 <= len(self.direct_key) <= _MAX_API_KEY_BYTES or any(
            not 0x21 <= ord(character) <= 0x7E for character in self.direct_key
        ):
            raise ValueError("Pi API-key material is malformed")

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str], *, state_path: Path | None = None
    ) -> PiA2InstallationConfig:
        if "HAMSTERDAN_PI_API_KEY_FILE" in environment:
            raise ValueError("retired Pi credential-file configuration is present")
        names = (
            "HAMSTERDAN_PI_PROVIDER",
            "HAMSTERDAN_PI_MODEL",
            "HAMSTERDAN_PI_API_KEY",
            "HAMSTERDAN_PI_CLI_PATH",
            "HAMSTERDAN_PI_NODE_PATH",
            "HAMSTERDAN_PI_PACKAGE_ROOT",
        )
        if any(not environment.get(name) for name in names):
            raise ValueError("Agenticus requires explicit direct-key and Pi runtime paths")
        config = cls(
            environment[names[0]],
            environment[names[1]],
            environment[names[2]],
            *(Path(environment[name]) for name in names[3:]),
        )
        if any(not path.is_absolute() for path in (config.cli_path, config.node_path, config.package_root)):
            raise ValueError("Agenticus installation paths must be absolute")
        if state_path is not None:
            _verify_installation_binding(Path(state_path) / "pi-a2", config.provider, config.model)
        return config


class OneShotApiKeySupplier:
    """Transfer one erasable direct-key buffer at most once."""

    def __init__(self, loader: Callable[[], bytearray]) -> None:
        if not callable(loader):
            raise TypeError("Pi A2 authority loader must be callable")
        self._loader = loader
        self._spent = False
        self._lock = threading.Lock()

    def __call__(self) -> bytearray:
        with self._lock:
            if self._spent:
                raise RuntimeError("Pi A2 authority supplier is already spent")
            self._spent = True
        value = self._loader()
        if not isinstance(value, bytearray) or not value:
            if isinstance(value, bytearray):
                _erase(value)
            raise RuntimeError("Pi A2 authority supplier returned invalid material")
        return value


class PersistentKeyOperations:
    """Authenticate retained opaque connection state with erasable per-connection keys."""

    def __init__(self, root: Path) -> None:
        self._root = _private_directory(root)
        self._lock = threading.RLock()

    def seal(self, context: KeyContext, plaintext: bytearray) -> bytes:
        if not isinstance(context, KeyContext) or not isinstance(plaintext, bytearray):
            raise TypeError("Pi A2 key sealing requires exact context and erasable plaintext")
        with self._lock:
            key = self._load_or_create(context.connection_id)
            nonce = os.urandom(_NONCE_BYTES)
            try:
                return _KEY_VERSION + nonce + AESGCM(key).encrypt(nonce, plaintext, context.authenticated_data())
            except Exception:  # noqa: BLE001 - key failures cross a secret-safe host boundary
                raise KeyOperationError("opaque connection state could not be sealed") from None

    def open(self, context: KeyContext, ciphertext: bytes) -> bytearray:
        if not isinstance(context, KeyContext) or not isinstance(ciphertext, bytes):
            raise TypeError("Pi A2 key opening requires exact context and ciphertext")
        if len(ciphertext) <= 1 + _NONCE_BYTES or not ciphertext.startswith(_KEY_VERSION):
            raise KeyOperationError("opaque connection state is malformed")
        with self._lock:
            key = self._load(context.connection_id)
            nonce = ciphertext[1 : 1 + _NONCE_BYTES]
            try:
                return bytearray(
                    AESGCM(key).decrypt(nonce, ciphertext[1 + _NONCE_BYTES :], context.authenticated_data())
                )
            except InvalidTag:
                raise KeyOperationError("opaque connection state failed authentication") from None
            except Exception:  # noqa: BLE001 - key failures cross a secret-safe host boundary
                raise KeyOperationError("opaque connection state could not be opened") from None

    def erase(self, connection_id: str) -> KeyErasureEvidence:
        path = self._path(connection_id)
        with self._lock:
            try:
                path.unlink()
                descriptor = os.open(self._root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            except FileNotFoundError:
                pass
            except OSError:
                raise KeyOperationError("opaque connection key could not be erased") from None
        return KeyErasureEvidence(connection_id, True)

    def _load_or_create(self, connection_id: str) -> bytes:
        try:
            return self._load(connection_id)
        except KeyOperationError:
            pass
        path = self._path(connection_id)
        key = os.urandom(_KEY_BYTES)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return self._load(connection_id)
        try:
            try:
                if os.write(descriptor, key) != len(key):
                    raise KeyOperationError("opaque connection key could not be persisted")
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except BaseException:
            path.unlink(missing_ok=True)
            _sync_directory(self._root)
            raise
        _sync_directory(self._root)
        return self._load(connection_id)

    def _load(self, connection_id: str) -> bytes:
        path = self._path(connection_id)
        try:
            metadata = path.lstat()
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_uid != os.geteuid()
                or metadata.st_size != _KEY_BYTES
            ):
                raise KeyOperationError("opaque connection key is unavailable")
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                current = os.fstat(descriptor)
                if (current.st_dev, current.st_ino) != (metadata.st_dev, metadata.st_ino):
                    raise KeyOperationError("opaque connection key changed while opening")
                key = os.read(descriptor, _KEY_BYTES + 1)
            finally:
                os.close(descriptor)
        except KeyOperationError:
            raise
        except OSError:
            raise KeyOperationError("opaque connection key is unavailable") from None
        if len(key) != _KEY_BYTES:
            raise KeyOperationError("opaque connection key is unavailable")
        return key

    def _path(self, connection_id: str) -> Path:
        if not isinstance(connection_id, str) or not connection_id:
            raise ValueError("connection identity must not be empty")
        return self._root / f"{sha256(connection_id.encode()).hexdigest()}.key"


def compose_owned_pi_a2(state_path: Path, installation: PiA2InstallationConfig | None = None) -> PiA2RuntimeHost:
    """Compose the production A2 boundary without consulting ambient authority."""

    root = _private_directory(state_path / "pi-a2")
    provider = PI_PROVIDER if installation is None else installation.provider
    model = PI_MODEL if installation is None else installation.model
    _bind_installation(root, provider, model)
    workspace = _private_directory(root / "workspace")
    authority = PiA2DirectAuthority(
        ConnectionIdentity(_CONNECTION_ID, provider, _ACCOUNT_FINGERPRINT, "api-key"),
        PersistentKeyOperations(root / "keys"),
        OneShotApiKeySupplier(
            _authority_unavailable if installation is None else lambda: bytearray(installation.direct_key, "ascii")
        ),
    )
    config = PiA2RuntimeHostConfig(
        state_root=root / "runtime-host",
        working_directory=workspace,
        provider=provider,
        model=model,
        host_id="hamsterdan-pi-a2",
        capabilities=_CAPABILITIES,
        max_tool_calls=32,
        cli_path=None if installation is None else str(installation.cli_path),
        node_path=None if installation is None else str(installation.node_path),
        package_root=None if installation is None else str(installation.package_root),
    )
    return compose_pi_a2_runtime(config=config, authority=authority)


def _authority_unavailable() -> bytearray:
    raise RuntimeError("Pi A2 direct authority is not enabled")


def _private_directory(path: Path) -> Path:
    selected = Path(path)
    if selected.is_symlink():
        raise ValueError("Pi A2 host directory must not be a symlink")
    selected.mkdir(mode=0o700, parents=True, exist_ok=True)
    selected.chmod(0o700)
    metadata = selected.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o700 or metadata.st_uid != os.geteuid():
        raise ValueError("Pi A2 host directory must be owned and private")
    return selected.resolve()


def _installation_value(provider: str, model: str) -> bytes:
    return f"{provider}\n{model}\n".encode("ascii")


def _read_installation_binding(path: Path) -> bytes:
    try:
        metadata = path.lstat()
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_uid != os.geteuid()
            or not 0 < metadata.st_size <= 256
        ):
            raise ValueError("Pi A2 installation binding is unsafe")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            opened = os.fstat(descriptor)
            value = os.read(descriptor, 257)
            current = os.fstat(descriptor)
        finally:
            os.close(descriptor)
    except FileNotFoundError:
        raise
    except OSError:
        raise ValueError("Pi A2 installation binding cannot be inspected safely") from None
    if (
        (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
        != (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns)
        or (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns)
        != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
        or len(value) != metadata.st_size
    ):
        raise ValueError("Pi A2 installation binding changed during inspection")
    return value


def _verify_installation_binding(root: Path, provider: str, model: str) -> None:
    if root.is_symlink():
        raise ValueError("Pi A2 host directory must not be a symlink")
    if not root.exists():
        return
    metadata = root.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o700 or metadata.st_uid != os.geteuid():
        raise ValueError("Pi A2 host directory must be owned and private")
    binding = root / "installation"
    expected = _installation_value(provider, model)
    try:
        actual = _read_installation_binding(binding)
    except FileNotFoundError:
        retained = tuple(path for path in root.iterdir() if not path.name.startswith(".installation-"))
        if retained and expected != _installation_value(PI_PROVIDER, PI_MODEL):
            raise ValueError("existing Pi A2 state is bound to a different provider/model") from None
        return
    if actual != expected:
        raise ValueError("existing Pi A2 state is bound to a different provider/model")


def _bind_installation(root: Path, provider: str, model: str) -> None:
    _verify_installation_binding(root, provider, model)
    binding = root / "installation"
    try:
        actual = _read_installation_binding(binding)
    except FileNotFoundError:
        pass
    else:
        if actual != _installation_value(provider, model):
            raise ValueError("existing Pi A2 state is bound to a different provider/model")
        return
    value = _installation_value(provider, model)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".installation-", dir=root)
    temporary = Path(temporary_name)
    try:
        try:
            os.fchmod(descriptor, 0o600)
            if os.write(descriptor, value) != len(value):
                raise OSError("short installation binding write")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        try:
            os.link(temporary, binding)
        except FileExistsError:
            _verify_installation_binding(root, provider, model)
        else:
            _sync_directory(root)
    finally:
        temporary.unlink(missing_ok=True)


def _erase(value: bytearray) -> None:
    for index in range(len(value)):
        value[index] = 0


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
