# !/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'Doris Qian'

import asyncio, logging, aiomysql


def log(sql, args=()):
	logging.info('SQL: %s' % sql)


async def create_pool(loop, **kw):
	logging.info('create database connection pool...')
	global __pool
	__pool = await aiomysql.create_pool(
		host = kw.get('host', 'localhost'),
		port = kw.get('port', 3306),
		user = kw['user'],
		pwd = kw['password'],
		db = kw['db'],
		charset = kw.get('charset', 'utf-8'),
		autocommit = kw.get('autcommit', True),
		maxsize = kw.get('maxsize', 10),
		minsize = kw.get('minsize', 1),
		loop = loop
		)


async def select(sql, args, size = None):
	log(sql, args)
	global __pool
	async with __pool.get() as conn:
		async with conn.cursor(aiomysql.DictCursor) as cur:
			await cur.execute(sql.replace('?', '%s'), args or ())
			if size:
				rs = await cur.fetchmany(size)
			else:
				rs = await cur.fetchall()
		logging.info('rows returned: %s' % len(rs))
		return rs


async def execute(sql, args, autocommit=True):
	log(sql)
	global __pool
	async with __pool.get() as conn:
		if not autocommit:
			await conn.begin()
		try:
			async with conn.cursor(aiomysql.DictCursor) as cur:
				await cur.execute(sql.replace('?', '%s'), args)
				affected = cur.rowcount
			if not autocommit:
				await conn.commit()
		except BaseException as e:
			if not autocommit:
				await conn.roolback()
			raise
		return affected


def create_args_string(num):
	L = []
	for n in range(num):
		L.append('?')
	return ','.join(L)

#定义一个字段的属性，包括其数据类型，是否为主键，是否有默认值及字段名
class Field(object):
	def __init__(self, name, column_type, primary_key, default):
		self.name = name
		self.column_type = column_type
		self.primary_key = primary_key
		self.default = default

	#双下划线表示重写str方法
	def __str__(self):
		return '<%s, %s:%s>' % (self.__class__.__name__, self.column_type, self.name)


class StringField(Field):
	def __init__(self, name=None, primary_key=False, default=None, ddl='varchar(100)'):
		super().__init__(name, ddl, primary_key, default)


class BooleanField(Field):
	def __init__(self, name=None, default=False):
		super().__init__(name, 'boolean', False, default)


class IntegerField(Field):
	def __init__(self, name=None, primary_key=False, default=0):
		super().__init__(name, 'bigint', primary_key, default)


class FloatField(Field):
	def __init__(self, name=None, primary_key=False, default=0.0):
		super().__init__(name, 'real', primary_key, default)


class TextField(Field):
	def __init__(self, name=None, default=None):
		super().__init__(name, 'text', False, default)


class ModelMetaclass(type):
	def __new__(cls, name, bases, attrs):
		if name == 'Model':
			return type.__new__(cls, name, bases, attrs)
		tableName = attrs.get('__table__', None) or name
		logging.info('found model: %s (table: %s)' % (name, tableName))
		mappings = dict()
		fields = []
		primarykey = None
		#attrs是一个表所有字段的集合，遍历所有字段k，其属性是v，如果是主键，将字段赋值给primarykey，否则添加到fields中
		for k, v in attrs.items():
			if isinstance(v, Field):
				logging.info('found mapping:%s ==> %s' % (k, v))
				mappings[k] = v
				if v.primary_key:
					if primarykey:
						raise StandardError('Duplicate primary key for field:%s' % k)
					primarykey = k
				else:
					fields.append(k)
		if not primarykey:
			raise StandardError('primary key not found.')
		for k in mappings.keys():
			attrs.pop(k)
		escaped_fields = list(map(lambda f: '`%s`' % f, fields))#``避免与sql关键字冲突
		print(escaped_fields)
		attrs['__mappings__'] = mappings
		attrs['__table__'] = tableName
		attrs['__field__'] = fields#除主键外的属性名
		attrs['__select__'] = 'select `%s`,%s from `%s`' % (primarykey, ','.join(escaped_fields), tableName)
		attrs['__insert__'] = 'insert into `%s` (%s, `%s`) values (%s)' % (tableName, ', '.join(escaped_fields), primarykey, create_args_string(len(escaped_fields) + 1))
		attrs['__update__'] = 'update `%s` set %s where `%s`=?' % (tableName, ','.join(map(lambda f: '`%s`=?' % (mappings.get(f).name or f), fields)), primarykey)
		attrs['__delete__'] = 'delete from `%s` where `%s`=?' % (tableName, primarykey)
		print(attrs['__insert__'])
		print(attrs['__select__'])
		return type.__new__(cls, name, bases, attrs)


class Model(dict, metaclass=ModelMetaclass):
	def __init__(self, **kw):
		super(Model, self).__init__(**kw)


	def __getattr__(self, key):
		try:
			return self[key]
		except KeyError:
			raise AttributeError(r"'Model' object has no attribute '%s'" % key)


	def __setattr__(self, key, value):
		self[key] = value


	def getValue(self, key):
		return getattr(self, key, None)


	def getValueOrDefault(self, key):
		value = getattr(self, key, None)
		if value is None:
			filed = self.__mappings__[key]
			if field.default is not None:
				#callabe判断对象能否被调用
				value = field.default() if callable(field.default) else field.default
				logging.debug('using default value for %s:%s' % (key, str(value)))
				setattr(self, key, value)
		return value


	@classmethod
	async def findAll(cls, where=None, args=None, **kw):
		'find object by where clause'
		sql = [cls.__select__]
		if where:
			sql.append('where')
			sql.append(where)
		if args is None:
			args=[]
		orderBy = kw.get('orderBy', None)
		if orderBy:
			sql.append('order by')
			sql.append(orderBy)
		limit = kw.get('limit', None)
		if limit is not None:
			sql.append('limit')
		

	async def save(self):
		#print(self.__fields__)
		args = list(map(self.getValueOrDefault, self.__fields__))
		args.append(self.getValueOrDefault(self.__primary_key__))
		rows = await execute(self.__insert__, args)
		if rows != 1:
			logging.info('failed to insert record: affected rows: %s' % rows)

class User(Model):
    # 定义类的属性到列的映射
    id = IntegerField("id", True)
    name = StringField("username")
    email = StringField("email")
    password = StringField("password")
    print(id)


# 创建一个实例
u = User(id=12345, name="ReedSun", email="sunhongzhao@foxmail.com", password="nicaicai")

loop = asyncio.get_event_loop()
loop.run_until_complete(u.save())
loop.run_forever()