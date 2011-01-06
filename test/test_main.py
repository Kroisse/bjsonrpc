import unittest
import sys
sys.path.insert(0, "../")
import bjsonrpc
from bjsonrpc.exceptions import ServerError

import testserver1
import math
from types import ListType

class TestJSONBasics(unittest.TestCase):
    def setUp(self):
        #testserver1.start()
        self.conn = bjsonrpc.connect()
        
    def tearDown(self):
        #testserver1.stop()
        pass
        
    def test_call(self):
        """ 
            Call to remote without parameters
        """
        rcall = self.conn.call 
        for i in range(30):
            pong = rcall.ping()
            self.assertEqual(pong, "pong")
    
    def test_call2params(self):
        """
            Call to remote with 2 parameters
        """
        rcall = self.conn.call 
        
        pairs = [
                 (941, -499), (1582, 1704),
                 (-733, 119), (-967, 1755),
                 (95, 286), (1866, -954),
                 (495, -241), (966, 994),
                 (1975, -758), (1939, 1699),
                 (-42, 1018), (44, -346),
                 (-621, -77), (-525, -804),
                 (1537, 417), (1851, 1660),
                 (-293, 1391), (-710, -796),
                 (1990, -542), (-624, -115), 
                 ]
        for x, y in pairs:
            added = rcall.add2(x, y)
            self.assertEqual(added,  x+y)
            
        
    def test_callNparams(self):
        """
            Call to remote with N parameters
        """
        rcall = self.conn.call 
        for i in range(50):
            tosum = [ x + i * 3 + x % 10  for x in range(10+i*4)]
            added = rcall.addN(*tosum)
            self.assertEqual(added,  sum(tosum))
            
        
    def test_float(self):
        """
            Call to remote with float parameters
        """
        rcall = self.conn.call 
        precision = 10**6
        for i in range(50):
            # make sure that the sum of this list is a float. Try to get complex floats.
            tosum = [ math.sin(x + i * 3 + x % 10) * 1999 / float(i+math.pi) for x in range(10+i*4)] 
            added = rcall.addN(*tosum)
            
            self.assertNotEqual(added, int(added)) # Ok, this can be equal, but this test should fail in this case
            self.assertAlmostEqual(added,  sum(tosum))
        
    def test_nested_list(self):
        """
            Call with a nested list
        """
        rcall = self.conn.call 
        
        nlist = []
        tot = 0
        for i in range(10):
            ilist = [ (n% 3) *2 + n + i%2 + i * 4  for n in range(10)]
            tot += sum(ilist)
            nlist.append(ilist)
        
        result = rcall.addnlist(nlist)
        self.assertEqual(result, tot)
        
    def test_tuple(self):
        """
            Tuples should be converted to lists
        """
        rcall = self.conn.call 
        result = rcall.getabc()
        self.assertTrue(isinstance(result, ListType))
        
        
    def test_kwparams(self):
        """
            Call remote using keyword parameters
        """
        rcall = self.conn.call 
        result = rcall.getabc(a=1, b=2, c=3)
        self.assertEqual(result, [1, 2, 3])
        
        result = rcall.getabc(b=1, c=2, a=3)
        self.assertEqual(result, [3, 1, 2])
        
        result = rcall.getabc(b="b", c="c", a="a")
        self.assertEqual(result, ["a", "b", "c"])
        
        result = rcall.getabc(c="c",  b="b")
        self.assertEqual(result, [None, "b", "c"])
        
    def test_commonerrors(self):
        rcall = self.conn.call 
        self.assertRaises(ServerError,  rcall.myfun) # inexistent method
        self.assertRaises(ServerError,  rcall.add) # not enough parameters
        self.assertRaises(ServerError,  rcall.getabc, j=32) # "j" parameter unknown
        self.assertRaises(ServerError,  rcall.add,  2, 3, 4,) # too parameters
        
        
        
        
        
        
        
        



if __name__ == '__main__':
    testserver1.start()
    unittest.main()
    testserver1.stop()
