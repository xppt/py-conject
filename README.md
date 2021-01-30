Conject
===

This library automates DI - allowing to create dependencies by its declarative description.
Features:
- Creates application components hierarchy automatically.
- Eliminates the need to implemenent config files support - allows you to configure any application component out of
the box, select implementations and link them together.
- Makes it easy to finalize components.
- Supports synchronous and asynchronous interfaces.
- Doesn't require components code modification (assuming they are written in DI-compatible style).

Example
---

Let's assume we have a simple http service:
```python
class HttpClient(abc.ABC):
    @abc.abstractmethod
    def request(self, method: str, url: str):
        raise NotImplementedError


class MockHttpClient(HttpClient):
    def request(self, method: str, url: str):
        ...  # return fake response


class PooledHttpClient(HttpClient):
    def __init__(self, proxy: str, user_agent: str):
        ...

    def request(self, method: str, url: str):
        ...

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        ...  # cleanup


class FbApiClient:
    def __init__(self, http_client: HttpClient, access_token: str, api_ver: str):
        ...

    def get_user_info(self, user_id: str) -> dict:
        ...  # use HttpClient to fetch user info


class FetchFbUserHandler:
    def __init__(self, fb_api_client: FbApiClient):
        ...

    def __call__(self, req):
        ...  # use FbApiClient.get_user_info and return


def create_http_app(fetch_fb_user_handler: FetchFbUserHandler):
    http_app = HttpApp([
        ('GET', '/fetch_fb_user/', fetch_fb_user_handler),
    ])
    return http_app
```

In order to fully construct our HttpApp we need to:
- Add config option to choose HttpClient implementation.
- Use `ExitStack` since `PooledHttpClient` is a context manager (while `MockHttpClient` isn't).
- Add config options for `proxy`, `user_agent`, `access_token`, `api_ver` parameters.

**conject** lets you avoid doing it manually.
```python
from conject import DepSpec, Impl


def run(config: dict) -> None:
    spec = DepSpec([
        Impl(Impl.Func,     'http_app',                 create_http_app),
        Impl(Impl.CtxMgr,   'pooled_http_client',       PooledHttpClient),
        Impl(Impl.Class,    'mock_http_client',         MockHttpClient),
        Impl(Impl.Class,    'fb_api_client',            FbApiClient),
        Impl(Impl.Class,    'fetch_fb_user_handler',    FetchFbUserHandler),
    ])

    with spec.start_container(config) as container:
        # get or create component with name 'http_app'
        #  expected type is optional, but allows type-checking
        http_app = container.get('http_app', HttpApp)

        ... # run_http_app(http_app)
```

Now we are able to control our components via configuration (formatted as toml for example):
```toml
[http_client]                 # component name, can be anything
-impl = 'pooled_http_client'  # use implementation named 'pooled_http_client'
user_agent = 'super-app/10'   # implementation params

[fb_api_client]
access_token = 'abcdefgh'
api_ver = '7.0'
```

Another possible config:
```toml
[proxied_http_client]
-impl = 'pooled_http_client'
proxy = 'my-squid:3128'

[proxied_fb_api_client]
-impl = 'fb_api_client'
http_client = {-ref = 'proxied_http_client'}  # use component named 'proxied_http_client'
access_token = 'fake_token'
api_ver = '7.0'

[http_app]
fb_api_client = {-ref = 'proxied_fb_api_client'}
```

**conject** allows some configuration parts to be omitted:
- If your component name matches implementation name component's `-impl` property can be omitted.
- You can omit implementation parameter. It will receive:
    - default value, if there is one in the factory signature;
    - component with the same name;
- If there is no need to set any of component's properties you can omit it completely.


Registering implementations
---
Factory types:
- `FactoryType.Value` - just value.
- `FactoryType.Func` - function returning implementation.
- `FactoryType.Class` - implementation-class.
- `FactoryType.GenFunc` - function generating implementation that can finalize it afterwards.
- `FactoryType.CtxMgr` - implementation context manager.
- `FactoryType.AFunc` - like `Func`, but async.
- `FactoryType.AGenFunc` - like `GenFunc`, but async.
- `FactoryType.ACtxMgr` - like `CtxMgr`, but async.

Factory can receive any parameters except for variadic (`*args`, `**kwargs`) and _positional-only_.

To register your implementations you need to create `DepSpec` (or `AsyncDepSpec`) object.

Registration ways:
```python
from conject import DepSpec, Impl

spec = DepSpec()  # you can pass impls to __init__

spec.add(Impl.CtxMgr,  'some_cls',  SomeCls)

spec.add_many([
    Impl(Impl.GenFunc,   'some_gen_func',   some_gen_func),
])

@spec.decorate(Impl.Func)
def some_func(some_cls: SomeCls):
    return 1
```


Creating a container
---
To create a container you need to enter context `spec.start_container(config: Any)`, where `config` will be used to
configure components.

Example:
```python
def run(spec: DepSpec) -> None:
    config = {'auth_provider': {'-impl': 'google_auth_provider'}}
    with spec.start_container(config) as container:
        auth_provider = container.get('auth_provider')
        assert isinstance(auth_provider, GoogleAuthProvider)
```


Using a container
---
Dependency container lazily creates components and manages their lifetime.

`def conject.Container.get(component_name: str) -> Any`

`async def conject.AsyncContainer.get(component_name: str) -> Any`

You can fetch any component by calling `get`. It will create every component dependency during this call.

These created objects will be finalized after `spec.start_container()` context exit only. The order of finalization will
be the reversed order of their creation.

Usually you will need only one container that runs for a whole program lifetime.


Components configuration
---

Config should be a dict in which every key describes one component. Value is also a dict with options:
- `-impl` is a special option, it allows you to select implementation name for this component. It could be omitted.
- All other options represents factory parameters. Besides simple values, you can use special ones:

    - `{'-ref': '<component_name>'}`

        Pass another component by its name.

    - `{'-expr': '<expression>'}`

        Pass result of evaluation of python-expression.

        The expression may depend on other components from `refs` namespace, e.g. `refs.other_component`.

        Example:
        ```python
        import os
        spec.add(Impl.Value, 'environ', os.environ)
        spec.add(Impl.Class, 'fb_api_client', FbApiClient)
        ```

        Config (formatted as toml):
        ```toml
        [fb_api_client]
        access_token = {-expr = 'refs.environ["FB_API_ACCESS_TOKEN"]'}
        ```

Special options `-ref`/`-expr` can also be used inside lists and dicts (including nested).


Type checking
---
In case your factories are type-annotated, **conject** will check its parameters in runtime. This is done via
**pydantic** library.

Also this allows you to pass e.g. `datetime` param from your toml configuration. To get the list of supported types see
[pydantic docs](https://pydantic-docs.helpmanual.io/usage/types/).

**Caveat**: your mutable parameter values (including dict/list/dataclass instances) will be rebuilt from scratch, so you
may not receive the same instance you've expected.


Utils
---
`def conject.utils.load_package_recursively(package_name: str) -> None`

Recursively import all package's modules. Doesn't handle namespace packages for now.

`def conject.utils.skip_type_check(value: Any) -> SkipTypeCheck`

Ask conject to assume this value is  correct as any param type.
