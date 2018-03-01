# !/usr/bin/env python3
# -*- coding: utf-8 -*-

import functools, inspect, asyncio, logging, os
from aiohttp import web
from urllib import parse
from apis import APIError

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s',
                    datefmt='%a, %d %b %Y %H:%M:%S')

__author__ = 'Doris Qian'


def get(path):
    """
    Define decorator @get('/path')
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            return func(*args, **kw)

        wrapper.__method__ = 'GET'
        wrapper.__route__ = path
        return wrapper

    return decorator


def post(path):
    """
    Define decorator @post('/path')
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            return func(*args, **kw)

        wrapper.__method__ = 'POST'
        wrapper.__route__ = path
        return wrapper

    return decorator


'''
1.处理URL和函数之间关系的程序称为路由。
2.在Flask程序中定义路由的最简便方式就是使用程序实例提供的app.route修饰器，把修饰的函数注册为路由。
例：

@app.route('/')
def index():
    return <h1>Hello World!</h1>

index()函数在例子中被注册为程序根地址的处理程序，index()函数的返回值称为响应，是客户端收到的内容。 
index()函数就被称为视图函数（view function）。 
app实例中调用route方法，参数为’/’。
'''


# 使用inspect模块，检查视图函数的参数

# inspect.Parameter.kind 类型：  
# POSITIONAL_ONLY          位置参数  
# KEYWORD_ONLY             命名关键词参数  
# VAR_POSITIONAL           可选参数 *args  
# VAR_KEYWORD              关键词参数 **kw  
# POSITIONAL_OR_KEYWORD    位置或必选参数  


def get_required_kw_args(fn):  # 获取无默认值的命名关键词参数
    """
    def foo(a, b = 10, *c, d,**kw): pass
    sig = inspect.signature(foo) ==> <Signature (a, b=10, *c, d, **kw)>
    sig.parameters ==>  mappingproxy(OrderedDict([('a', <Parameter "a">), ...]))
    sig.parameters.items() ==> odict_items([('a', <Parameter "a">), ...)])
    sig.parameters.values() ==>  odict_values([<Parameter "a">, ...])
    sig.parameters.keys() ==>  odict_keys(['a', 'b', 'c', 'd', 'kw'])
    """
    args = []
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY and param.default == inspect.Parameter.empty:
            args.append(name)
    return tuple(args)


def get_named_kw_args(fn):  # 获取命名关键词参数
    args = []
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            args.append(name)
    return tuple(args)


def has_named_kw_args(fn):  # 判断是否有命名关键词参数
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            return True


def has_var_kw_arg(fn):  # 判断是否有关键词参数
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            return True


def has_request_arg(fn):  # 判断是否含有名叫'request'的参数，且位置在最后
    params = inspect.signature(fn).parameters
    found = False
    for name, param in params.items():
        if name == 'request':
            found = True
            continue
        if found and (
                            param.kind != inspect.Parameter.VAR_KEYWORD and
                            param.kind != inspect.Parameter.VAR_POSITIONAL and
                        param.kind != inspect.Parameter.KEYWORD_ONLY):
            # 若判断为True，表明param只能是位置参数。且该参数位于request之后，故不满足条件，报错。
            raise ValueError(
                'request parameter must be the last named parameter in function:%s%s' % (fn.__name__, str(sig)))
    return found


# 定义RequestHandler从视图函数中分析其需要接受的参数，从web.Request中获取必要的参数  
# 调用视图函数，然后把结果转换为web.Response对象，符合aiohttp框架要求  
class RequestHandler(object):
    def __init__(self, app, fn):
        self._app = app
        self._func = fn
        self._required_kw_args = get_required_kw_args(fn)
        self._named_kw_args = get_named_kw_args(fn)
        self._has_request_arg = has_request_arg(fn)
        self._has_named_kw_args = has_named_kw_args(fn)
        self._has_var_kw_arg = has_var_kw_arg(fn)

    # 1.定义kw，用于保存request参数
    # 2.判断视图函数是否存在关键词参数，如果存在根据POST或者GET方法将request请求内容保存到kw  
    # 3.如果kw为空（说明request无请求内容），则将match_info列表里的资源映射给kw；若不为空，把命名关键词参数内容给kw  
    # 4.完善_has_request_arg和_required_kw_args属性 
    async def __call__(self, request):
        kw = None
        if self._has_named_kw_args or self._has_var_kw_arg:
            if request.method == 'POST':
                # 根据request参数中的content_type使用不同解析方法：
                if request.content_type == None:
                    return web.HTTPBadRequest(text='Miss content_type.')
                ct = request.content_type.lower()
                if ct.startwith('application/json'):  # json格式数据
                    params = await request.json()  # 仅解析body字段的json数据
                    if not isinstance(params, dict):
                        return web.HTTPBadRequest(text='JSON body must be object.')
                    kw = params
                # form表单请求的解码形式
                elif ct.startwith('application/x-www-form-urlencoded') or ct.startswith('multipart/form-data'):
                    params = await request.post()  # 返回post的内容中解析后的数据。dict-like对象。
                    kw = dict(**params)  # 组成dict，统一kw格式
                else:
                    return web.HTTPBadRequest(text='Unsupported Content-Type: %s' % request.content_type)
            if request.method == 'GET':
                qs = request.query_string  # 返回URL查询语句，?后的键值。string形式。
                if qs:
                    kw = dict()
                    '''''
                    解析url中?后面的键值对的内容 
                    qs = 'first=f,s&second=s' 
                    parse.parse_qs(qs, True).items() 
                    >>> dict([('first', ['f,s']), ('second', ['s'])]) 
                    '''
                    for k, v in parse.parse_qs(qs, True).items():  # 返回查询变量和值的映射，dict对象。True表示不忽略空格。
                        kw[k] = v[0]
        if kw is None:  # 若request中无参数
            # request.match_info返回dict对象。可变路由中的可变字段{variable}为参数名，传入request请求的path为值  
            # 若存在可变路由：/a/{name}/c，可匹配path为：/a/jack/c的request  
            # 则request.match_info返回{name = jack} 
            kw = dict(**request.match_info)
        else:  # request 有参数
            if self._has_named_kw_args and (not self._has_var_kw_arg):
                copy = dict()
				# 只保留命名关键词参数
                # remove all unamed kw:
                for name in self._named_kw_args:
                    if name in kw:
                        copy[name] = kw[name]
                kw = copy  # kw中只存在命名关键词参数
            # 将request.match_info中的参数传入kw
            # check named arg:
            for k, v in request.match_info.items():
                # 检查kw中的参数是否和match_info中的重复
                if k in kw:
                    logging.warn('Duplicate arg name in named arg and kw args: %s' % k)
                kw[k] = v
        if self._has_request_arg:  # 试图函数中存在request参数
            kw['request'] = request
        # check required kw:
        if self._required_kw_args:  # 视图函数存在无默认值的命名关键词参数
            for name in self._required_kw_args:
                if not name in kw:  # 若未传入必须参数值，报错。
                    return web.HTTPBadRequest('Missing argument: %s' % name)
        # 至此，kw为视图函数fn真正能调用的参数  
        # request请求中的参数，终于传递给了视图函数  
        logging.info('call with args: %s' % str(kw))
        try:
            r = await self._func(**kw)
            return r
        except APIError as e:
            return dict(error=e.error, data=e.data, message=e.message)


# 编写一个add_route函数，用来注册一个视图函数  
def add_route(app, fn):
    method = getattr(fn, '__method__', None)
    path = getattr(fn, '__route__', None)
    if method is None or path is None:
        raise ValueError('@get or @post not defined in %s' % fn.__name__)
    # 判断URL处理函数是否协程并且是生成器
    if not asyncio.iscoroutinefunction(fn) and not inspect.isgeneratorfunction(fn):
        # 将fn转换为协程
        fn = asyncio.coroutine(fn)
    logging.info(
        'add route %s %s => %s(%s)' % (method, path, fn.__name__, ','.join(inspect.signature(fn).parameters.keys())))
    # 在app中注册经RequestHandler类封装的视图函数
    app.router.add_route(method, path, RequestHandler(app, fn))


# add_route函数每次只能注册一个视图函数。若要批量注册视图函数，需要编写一个批注册函数add_routes。
# 希望只提供模块路径，批注册函数将自动导入其中的视图函数进行注册。


# 导入模块，批量注册视图函数  
def add_routes(app, module_name):
    n = module_name.rfind('.')  # 从右侧检索，返回索引。若无，返回-1。
    # 导入整个模块
    if n == -1:
        # __import__ 作用同import语句，但__import__是一个函数，并且只接收字符串作为参数
        # __import__('os',globals(),locals(),['path','pip'], 0) ,等价于from os import path, pip 
        mod = __import__(module_name, globals(), locals())
    else:
        name = module_name[(n + 1):]
        # 只获取最终导入的模块，为后续调用dir()
        mod = getattr(__import__(module_name[:n], globals(), locals(), [name]), name)
    for attr in dir(mod):  # dir()迭代出mod模块中所有的类，实例及函数等对象,str形式
        if attr.startswith('_'):
            continue
        fn = getattr(mod, attr)
        print(fn)
        # 确保是函数
        if callable(fn):
            # 确保视图函数存在method和path
            method = getattr(fn, '__method__', None)
            path = getattr(fn, '__route__', None)
            print(method, path)
            if method and path:
                # 注册
                add_route(app, fn)


# 编写add_static函数用于注册静态文件，只提供文件路径即可进行注册


# 添加静态文件，如image，css，javascript等  
def add_static(app):
    # 拼接static文件目录
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    app.router.add_static('/static/', path)
    logging.info('add static %s => %s' % ('/static/', path))
