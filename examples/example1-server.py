"""
    example1-server.py
    
    Example Server using jpc alternative library.
    
    Copyright (c) 2010 David Martinez Marti
    All rights reserved.

    Redistribution and use in source and binary forms, with or without
    modification, are permitted provided that the following conditions
    are met:
    1. Redistributions of source code must retain the above copyright
       notice, this list of conditions and the following disclaimer.
    2. Redistributions in binary form must reproduce the above copyright
       notice, this list of conditions and the following disclaimer in the
       documentation and/or other materials provided with the distribution.
    3. Neither the name of copyright holders nor the names of its
       contributors may be used to endorse or promote products derived
       from this software without specific prior written permission.

    THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
    ``AS IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED
    TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
    PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL COPYRIGHT HOLDERS OR CONTRIBUTORS
    BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
    CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
    SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
    INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
    CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
    ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
    POSSIBILITY OF SUCH DAMAGE.

"""

import sys
sys.path.insert(0,"../") # prefer local version
import bjsonrpc

import random


class MyHandler(bjsonrpc.BaseHandler):
    def _setup(self):
        super(type(self),self)._setup()
        self._add_method(self.addvalue,self.getrandom)
        self._add_method(self.gettotal,self.getcount)
        self._add_method(self.echo)
        self.value_count = 0
        self.value_total = 0
    
    def addvalue(self,number):
        n = float(number)
        self.value_count += 1
        self.value_total += n
        
    def getrandom(self):
        return random.randint(0,100)
    
    def gettotal(self):
        self._conn.notify.notify("total")
        return self.value_total
        
    def getcount(self):
        return self.value_count
        
    
    def echo(self, string):
        #print self._addr 
        #print self._conn 
        #print self._methods 
        print string
        return string
    

bjsonrpc.server(handler_factory=MyHandler, port = 10123, host = "0.0.0.0").serve()