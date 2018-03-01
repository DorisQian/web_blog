# !/usr/bin/env python3
# -*- coding: utf-8 -*-

import re, time, json, logging, hashlib, base64, asyncio
from models import User, Comment, Blog, next_id
from coroweb import get, post

__author__ = 'Doris Qian'

'url handlers'


@get('/')
async def index(request):
    users = await User.findAll()
    return {
        '__template__': 'test.html',
        'users': users
    }
