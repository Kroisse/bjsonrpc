"""
    bjson/connection.py
    
    Asynchronous Bidirectional JSON-RPC protocol implementation over TCP/IP
    
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

import socket, traceback, sys, threading
from types import MethodType, FunctionType

from bjsonrpc.proxies import Proxy
from bjsonrpc.request import Request
from bjsonrpc.exceptions import EofError, ServerError

import bjsonrpc.jsonlib as json

class RemoteObject(object):
    """
        Represents a object in the server-side (or client-side when speaking from
        the point of view of the server) . It remembers its name in the server-side
        to allow calls to the original object.
        
        Parameters:
        
        **conn**
            Connection object which holds the socket to the other end 
            of the communications
        
        **obj**
            JSON object (Python dictionary) holding the values recieved.
            It is used to retrieve the properties to create the remote object.
            (Initially only used to get object name)
            
        Example::
        
            list = conn.call.newList()
            for i in range(10): list.notify.add(i)
            
            print list.call.getitems()
        
    """
    
    name = None 
    # Name of the object in the server-side. 
    
    call = None 
    # Synchronous Proxy. It forwards your calls to it to the other end, waits
    # the response and returns the value.
    
    method = None 
    # Asynchronous Proxy. It forwards your calls to it to the other end and
    # inmediatelly returns a *request.Request* instance.
    
    notify = None 
    # Notification Proxy. It forwards your calls to it to the other end and
    # tells the server to not response even if there's any error in the call.
    # Returns *None*.
    
    @property
    def connection(self): 
        """
            Public property to get the internal connection object.
        """
        return self._conn
    
    def __init__(self, conn, obj):
        self._conn = conn
        self.name = obj['__remoteobject__']
        
        self.call = Proxy(self._conn, obj=self.name, sync_type=0)
        self.method = Proxy(self._conn, obj=self.name, sync_type=1)
        self.notify = Proxy(self._conn, obj=self.name, sync_type=2)
    
    def __del__(self):
        self._close()
        
    def _close(self):
        """
            Internal close method called both by __del__() and public 
            method close()
        """
        self.call.__delete__()
        self.name = None
        
    def close(self):
        """
            Closes/deletes the remote object. The server may or may not delete
            it at this time, but after this call we don't longer have any access to it.
            
            This method is automatically called when Python deletes this instance.
        """
        return self._close()
        
        

class Connection(object): # TODO: Split this class in simple ones
    """ 
        Represents a communiation tunnel between two parties.
        
        **sck**
            Connected socket to use. Should be an instance of *socket.socket* or
            something compatible.
        
        **address**
            Address of the other peer in (host,port) form. It is only used to 
            inform handlers about the peer address.
        
        **handler_factory**
            Class type inherited from BaseHandler which holds the public methods.
            It defaults to *NullHandler* meaning no public methods will be 
            avaliable to the other end.
        
    """
    _maxtimeout = {
        'read' : 5,    # default maximum read timeout.
        'write' : 5,   # default maximum write timeout.
    }
    
    @classmethod
    def setmaxtimeout(cls, operation, value):
        """
            Set the maximum timeout in seconds for **operation** operation.
            
            Parameters:
            
            **operation**
                The operation which has to be configured. Can be either 'read'
                or 'write'.
            
            **value**
                The timeout in seconds as a floating number. If is None, will 
                block until succeed. If is 0, will be nonblocking.
            
        """
        assert(operation in ['read', 'write'])
        cls._maxtimeout[operation] = value
    
    @classmethod
    def getmaxtimeout(cls, operation):
        """
            Get the maximum timeout in seconds for **operation** operation.
            
            Parameters:
            
            **operation**
                The operation which has to be configured. Can be either 'read'
                or 'write'.
            
            **(return value)**
                The timeout in seconds as a floating number or None.
            
        """
        if operation not in cls._maxtimeout: 
            return None
            
        return cls._maxtimeout[operation]
    
    call = None 
    # Synchronous Proxy. It forwards your calls to it to the other end, waits
    # the response and returns the value.
    
    method = None 
    # Asynchronous Proxy. It forwards your calls to it to the other end and
    # inmediatelly returns a *request.Request* instance.
    
    notify = None 
    # Notification Proxy. It forwards your calls to it to the other end and
    # tells the server to not response even if there's any error in the call.
    # Returns *None*.
    
    def __init__(self, sck, address = None, handler_factory = None):
        self._debug_socket = False
        self._debug_dispatch = False
        self._buffer = ''
        self._sck = sck
        self._address = address
        self._handler = handler_factory 
        if self._handler: 
            self.handler = self._handler(self)
            
        self._id = 0
        self._requests = {}
        self._objects = {}

        self.scklock = threading.Lock()
        self.call = Proxy(self, sync_type=0)
        self.method = Proxy(self, sync_type=1)
        self.notify = Proxy(self, sync_type=2)
        self._wbuffer = []
    
    @property
    def socket(self): 
        """
            public property that holds the internal socket used.
        """
        return self._sck
        
    def get_id(self):
        """
            Retrieves a new ID counter. Each connection has a exclusive ID counter.
            
            It is mainly used to create internal id's for calls.
        """
        self._id += 1
        return self._id 
        
    def load_object(self, obj):
        """
            Helper function for JSON loads. Given a dictionary (javascript object) returns
            an apropiate object (a specific class) in certain cases.
            
            It is mainly used to convert JSON hinted classes back to real classes.
            
            Parameters:
            
            **obj**
                Dictionary-like object to test.
                
            **(return value)**
                Either the same dictionary, or a class representing that object.
        """
        
        if '__remoteobject__' in obj: 
            return RemoteObject(self, obj)
            
        if '__objectreference__' in obj: 
            return self._objects[obj['__objectreference__']]
            
        if '__functionreference__' in obj:
            name = obj['__functionreference__']
            if '.' in name:
                objname, methodname = name.split('.')
                obj = self._objects[objname]
            else:
                obj = self.handler
                methodname = name
            method = obj.get_method(methodname)
            return method
        
        return obj
        
    def addrequest(self, request):
        """
            Adds a request to the queue of requests waiting for response.
        """
        assert(isinstance(request, Request))
        assert(request.request_id not in self._requests)
        self._requests[request.request_id] = request
    
    def dump_object(self, obj):
        """
            Helper function to convert classes and functions to JSON objects.
            
            Given a incompatible object called *obj*, dump_object returns a 
            JSON hinted object that represents the original parameter.
            
            Parameters:
            
            **obj**
                Object, class, function,etc which is incompatible with JSON 
                serialization.
                
            **(return value)**
                A valid serialization for that object using JSON class hinting.
                
        """
        # object of unknown type
        if type(obj) is FunctionType or type(obj) is MethodType :
            conn = getattr(obj, '_conn', None)
            if conn != self: 
                raise TypeError("Tried to serialize as JSON a handler for "
                "another connection!")
            return self._dump_functionreference(obj)
            
        if not isinstance(obj, object): 
            raise TypeError("JSON objects must be new-style classes")
            
        if not hasattr(obj, '__class__'): 
            raise TypeError("JSON objects must be instances, not types")
            
        if isinstance(obj, RemoteObject): 
            return self._dump_objectreference(obj)
            
        if hasattr(obj, 'get_method'): 
            return self._dump_remoteobject(obj)
            
        raise TypeError("Python object %s laks a 'get_method' and "
            "is not serializable!" % repr(obj))

    def _dump_functionreference(self, obj):
        """ Converts obj to a JSON hinted-class functionreference"""
        return { '__functionreference__' : obj.__name__ }

    def _dump_objectreference(self, obj):
        """ Converts obj to a JSON hinted-class objectreference"""
        return { '__objectreference__' : obj.name }
        
    def _dump_remoteobject(self, obj):
        """ 
            Converts obj to a JSON hinted-class remoteobject, creating
            a RemoteObject if necessary
        """
        
        # An object can be remotely called if :
        #  - it derives from object (new-style classes)
        #  - it is an instance
        #  - has an internal function _get_method to handle remote calls
        if not hasattr(obj, '__remoteobjects__'): 
            obj.__remoteobjects__ = {}
            
        if self in obj.__remoteobjects__:
            instancename = obj.__remoteobjects__[self] 
        else:
            classname = obj.__class__.__name__
            instancename = "%s_%04x" % (classname.lower(), self.get_id())
            self._objects[instancename] = obj
            obj.__remoteobjects__[self] = instancename
        return { '__remoteobject__' : instancename }

    def _dispatch_method(self, request):
        """
            Processes one request.
        """
        # TODO: Simplify this function or split it in small ones.
        req_id = request.get("id", None)
        req_method = request.get("method")
        req_args = request.get("params", [])
        if type(req_args) is dict: 
            req_kwargs = req_args
            req_args = []
        else:
            req_kwargs = request.get("kwparams", {})
            
        if req_kwargs: 
            req_kwargs = dict((str(k), v) for k, v in req_kwargs.iteritems())
            
        if '.' in req_method: # local-object.
            objectname, req_method = req_method.split('.')[:2]
            if objectname not in self._objects: 
                raise ValueError, "Invalid object identifier"
                
            if req_method == '__delete__': 
                req_object = None
                del self._objects[objectname]
                result = None
            else:
                req_object = self._objects[objectname]
        else:
            req_object = self.handler
            
        if req_object:
            try:
                req_function = req_object.get_method(req_method)
                result = req_function(*req_args, **req_kwargs)
            except ServerError, exc:
                if req_id is not None: 
                    return {'result': None, 'error': '%s' % (exc), 'id': req_id}
            except Exception:
                etype, evalue, etb = sys.exc_info()
                funargs = ", ".join(
                    [repr(x) for x in req_args] +  
                    ["%s=%s" % (k, repr(x)) for k, x in req_kwargs.iteritems()]
                    )
                if len(funargs) > 40: 
                    funargs = funargs[:37] + "..."
                
                print "(%s) In Handler method %s.%s(%s) " % (
                    req_object.__class__.__module__,
                    req_object.__class__.__name__,
                    req_method, 
                    funargs
                    )
                print "\n".join([ "%s::%s:%d %s" % (
                        filename, fnname, 
                        lineno, srcline  ) 
                    for filename, lineno, fnname, srcline 
                    in traceback.extract_tb(etb)[1:] ])
                print "Unhandled error: %s: %s" % (etype.__name__, evalue)
                    
                del etb
                if req_id is not None: 
                    return {
                        'result': None, 
                        'error': '%s: %s' % (etype.__name__, evalue), 
                        'id': req_id
                        }
        
        if req_id is None: 
            return None
        return {'result': result, 'error': None, 'id': req_id}

    def dispatch_until_empty(self):
        """
            Calls *read_and_dispatch* method until there are no more messages to
            dispatch in the buffer.
            
            Returns the number of operations that succeded.
            
            This method will never block waiting. If there aren't 
            any more messages that can be processed, it returns.
        """
        newline_idx = 0
        count = 0
        while newline_idx != -1:
            if not self.read_and_dispatch(timeout=0): 
                break
            count += 1
            newline_idx = self._buffer.find('\n')
        return count
                
                
    def read_and_dispatch(self, timeout=None):
        """
            Read one message from socket (with timeout specified by the optional 
            argument *timeout*) and dispatches that message.
            
            Parameters:
            
            **timeout** = None
                Timeout in seconds of the read operation. If it is None 
                (or ommitted) then the read will wait 
                until new data is available.
                
            **(return value)**
                True, in case of the operation has suceeded and **one** message
                has been dispatched. False, if no data or malformed data has 
                been received.
                
        """
        data = self.read(timeout=timeout)
        if not data: 
            return False 
        try:
            item = json.loads(data, self)  
            if type(item) is list: # batch call
                for i in item: 
                    self.dispatch_item(i)
            elif type(item) is dict: # std call
                self.dispatch_item(item)
            else: # Unknown format :-(
                print "Received message with unknown format type:" , type(item)
                return False
        except Exception:
            print traceback.format_exc()
            return False
            
        return True
        
            
             
    def dispatch_item(self, item):
        """
            Given a JSON item received from socket, determine its type and 
            process the message.
        """
        assert(type(item) is dict)
        response = None
        if 'id' not in item: 
            item['id'] = None
        
        if 'method' in item: 
            response = self._dispatch_method(item)
        elif 'result' in item: 
            assert(item['id'] in self._requests)
            request = self._requests[item['id']]
            del self._requests[item['id']]
            request.setresponse(item)
        else:
            response = {
                'result': None, 
                'error': "Unknown format", 
                'id': item['id']
                }
            
        if response is not None:
            try:
                self.write(json.dumps(response, self))
            except TypeError:
                print "response was:", repr(response)
                raise
        return True
    
    
    def proxy(self, sync_type, name, args, kwargs):
        """
        Call method on server.

        sync_type :: 
          = 0 .. call method, wait, get response.
          = 1 .. call method, inmediate return of object.
          = 2 .. call notification and exit.
          
        """
       
        data = {}
        data['method'] = name

        if sync_type in [0, 1]: 
            data['id'] = self.get_id()
            
        if len(args) > 0: 
            data['params'] = args
            
        if len(kwargs) > 0: 
            if len(args) == 0: 
                data['params'] = kwargs
            else: 
                data['kwparams'] = kwargs
            
        if sync_type == 2: # short-circuit for speed!
            self.write(json.dumps(data, self))
            return None
                    
        req = Request(self, data)
        if sync_type == 2: 
            return None
            
        if sync_type == 1: 
            return req
        
        return req.value

    def close(self):
        """
            Close the connection and the socket. 
        """
        try:
            self._sck.shutdown(socket.SHUT_RDWR)
        except socket.error:
            pass
        self._sck.close()
    
    def write_line(self, data):
        """
            Write a line *data* to socket. It appends a `\\n` at
            the end of the *data* before sending it.
            
            The string MUST NOT contain `\\n` otherwise an AssertionError will
            raise.
            
            Parameters:
            
            **data**
                String containing the data to be sent.
        """
        assert('\n' not in data)
        if self._debug_socket: 
            print "<:%d:" % len(data), data
            
        self._wbuffer += list(str(data + '\n'))
        sbytes = 0
        while len(self._wbuffer) > 0:
            try:
                sbytes = self._sck.send("".join(self._wbuffer))
            except IOError:
                print "Read socket error: IOError (timeout: %s)" % (
                    repr(self._sck.gettimeout())  )
                print traceback.format_exc(0)
                return ''
            except socket.error:
                print "Read socket error: socket.error (timeout: %s)" % (
                    repr(self._sck.gettimeout())  )
                print traceback.format_exc(0)
                return ''
            except:
                raise
            if sbytes == 0: 
                break
            self._wbuffer[0:sbytes] = []
        if len(self._wbuffer):
            print "warn: %d bytes left in write buffer" % len(self._wbuffer)
        return len(self._wbuffer)
            


    def read_line(self):
        """
            Read a line of *data* from socket. It removes the `\\n` at
            the end before returning the value.
            
            If the original packet contained `\\n`, the message will be decoded
            as two or more messages.
            
            Returns the line of *data* received from the socket.
        """
        data = self._readn()
        if len(data) and self._debug_socket: 
            print ">:%d:" % len(data), data
        return data
    
    def settimeout(self, operation, timeout):
        """
            configures a timeout for the connection for a given operation.
            operation is one of "read" or "write"
        """
        if operation in self._maxtimeout:
            maxtimeout = self._maxtimeout[operation]
        else:
            maxtimeout = None
            
        if maxtimeout is not None:
            if timeout is None or timeout > maxtimeout: 
                timeout = maxtimeout
            
        self._sck.settimeout(timeout)
            

    def write(self, data, timeout = None):
        """ 
            Standard function to write to the socket 
            which by default points to write_line
        """
        self.settimeout("write", timeout)
        self.scklock.acquire()
        ret = None
        try:
            ret = self.write_line(data)
        finally:
            self.scklock.release()
        
        return ret
    
    def read(self, timeout = None):
        """ 
            Standard function to read from the socket 
            which by default points to read_line
        """
        self.settimeout("read", timeout)
        ret = None
        self.scklock.acquire()
        try:
            ret = self.read_line()
        finally:
            self.scklock.release()
        return ret

    def _readn(self):
        """
            Internal function which reads from socket waiting for a newline
        """
        streambuffer = self._buffer
        pos = streambuffer.find('\n')
        #print "read..."
        #retry = 0
        while pos == -1:
            data = ''
            try:
                data = self._sck.recv(2048)
            except IOError, inst:
                print "Read socket error: IOError (timeout: %s)" % (
                    repr(self._sck.gettimeout())  )
                print inst.args
                val = inst.args[0]
                if val == 11: # Res. Temp. not available.
                    if self._sck.gettimeout() == 0: # if it was too fast
                        self._sck.settimeout(5)
                        continue
                        #time.sleep(0.5)
                        #retry += 1
                        #if retry < 10:
                        #    print "Retry ", retry
                        #    continue
                #print traceback.format_exc(0)
                return ''
            except socket.error, inst:
                print "Read socket error: socket.error (timeout: %s)" % (
                    repr(self._sck.gettimeout())  )
                print inst.args
                #print traceback.format_exc(0)
                return ''
            except:
                raise
            if not data:
                raise EofError(len(streambuffer))
            #print "readbuf+:",repr(data)
            streambuffer += data
            pos = streambuffer.find('\n')

        self._buffer = streambuffer[pos + 1:]
        streambuffer = streambuffer[:pos]
        #print "read:", repr(buffer)
        return streambuffer
        
    def serve(self):
        """
            Basic function to put the connection serving. Usually is better to 
            use server.Server class to do this, but this would be useful too if 
            it is run from a separate Thread.
        """
        try:
            while True: 
                self.read_and_dispatch()
        finally:
            self.close()