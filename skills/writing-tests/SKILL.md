---
name: writing-tests
description: Como escribir tests utiles — que testear, que NO testear, naming, estructura AAA, fixtures, mocks vs fakes vs reales. Cargala cuando el usuario pide tests, cuando agregas una feature nueva no trivial, o cuando arreglas un bug (test de regresion).
---

# Skill: writing-tests

## Cuando usarla
- El usuario pide "escribi tests para X"
- Agregaste logica nueva no trivial (no getters/setters, no glue)
- Arreglaste un bug — test de regresion
- Vas a refactorizar y necesitas safety net

## Cuando NO usarla
- Code de un solo uso, scripts experimentales
- Glue code obvio (definicion de constantes, re-exports)
- El usuario explicitamente dijo "sin tests"

## Que SI testear
- **Comportamiento publico**: lo que el codigo promete a sus callers
- **Edge cases**: empty, null, off-by-one, max int, unicode
- **Branches no obvios**: rama `else if` que es facil de olvidar
- **Bugs ya arreglados**: test que falla sin el fix, para que no vuelvan
- **Contratos entre modulos**: serializacion, schemas, formatos

## Que NO testear
- Implementacion interna (privates) — acoplas tests al refactor
- Cosas que el framework garantiza (no testees que SQLAlchemy hace SELECT)
- Constantes triviales
- 100% coverage como objetivo — coverage es subproducto, no meta

## Estructura AAA
```
def test_<sujeto>_<situacion>_<resultado_esperado>():
    # Arrange — setup
    user = make_user(email="a@b.com")

    # Act — la accion bajo test (una sola)
    result = login(user.email, "wrongpass")

    # Assert — un solo concepto verificado
    assert result.status == "rejected"
    assert result.reason == "bad_password"
```

## Naming
- Mal: `test_login`, `test_1`, `test_user`
- Bien: `test_login_with_wrong_password_returns_rejected`
- El nombre dice QUE situacion testeas y QUE esperas. Si el test falla, el nombre te dice lo suficiente sin leer el codigo.

## Mocks vs Fakes vs Reales
- **Real**: usar la cosa de verdad (DB en memoria SQLite, http test client). Default cuando es barato.
- **Fake**: implementacion alternativa simplificada (in-memory cache implementando misma interface). Bien para deps con IO real.
- **Mock**: simula y verifica llamadas. Usar cuando importa *que se llamo* (ej: "se mando el email"). Sobreuso acopla tests a implementacion.

Regla: si despues de refactor que no cambia comportamiento publico, los tests rompen → tenes demasiados mocks.

## Por stack

### FastAPI
```python
from fastapi.testclient import TestClient
client = TestClient(app)

def test_create_user_returns_201():
    r = client.post("/users", json={"email": "a@b.com", "password": "x"})
    assert r.status_code == 201
    assert r.json()["email"] == "a@b.com"
```
Overrides: `app.dependency_overrides[get_db] = lambda: test_db`

### SvelteKit
- Componentes: `@testing-library/svelte` + `vitest`
- E2E: Playwright (`@playwright/test`)
- Load functions: testeables como funciones puras pasandole un mock de `event`

### Rust / Actix
```rust
#[actix_web::test]
async fn test_health_returns_ok() {
    let app = test::init_service(App::new().service(health)).await;
    let req = test::TestRequest::get().uri("/health").to_request();
    let resp = test::call_service(&app, req).await;
    assert!(resp.status().is_success());
}
```

## Fixtures y factory pattern
Mejor que crear datos a mano repetido:
```python
def make_user(**overrides):
    defaults = {"email": "a@b.com", "name": "Alice", "active": True}
    return User(**{**defaults, **overrides})
```
Asi el test dice solo lo que importa: `make_user(active=False)`.

## Anti-patterns
- Tests que dependen del orden de ejecucion
- Tests que comparten estado mutable (DB no reseteada entre tests)
- Asserts gigantes que verifican 20 campos — si falla uno, no sabes cual
- `sleep(N)` en lugar de waits con condicion
- `try/except` dentro del test que swallowea el assert fail
- Tests que pasan SIN la implementacion (= no testean nada)

## Ejemplo de test de regresion
Si arreglaste el bug "usuarios sin email crashean el endpoint":
```python
def test_get_user_with_null_email_does_not_crash():
    user = db_insert_user(email=None)
    r = client.get(f"/users/{user.id}")
    assert r.status_code == 200
    assert r.json()["email"] is None
```
Este test FALLA sin tu fix y PASA con tu fix. Ese es el criterio.
