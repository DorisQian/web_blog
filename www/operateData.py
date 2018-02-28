# !/usr/bin/env python3
# -*- coding: utf-8 -*-

import orm,asyncio
from models import User, Blog, Comment

__author__ = 'Doris Qian'


loop = asyncio.get_event_loop()

async def operateData():
	await orm.create_pool(loop=loop, user='root', password='Anchiva@123', db='webblog')
	u = User(name='Test', email='test@example.com', password='1234567890', image='about:blank')
	await u.save()
	
loop.run_until_complete(operateData())
