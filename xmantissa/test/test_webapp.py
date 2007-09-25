
from zope.interface import implements

from twisted.trial.unittest import TestCase

from axiom.store import Store
from axiom.item import Item
from axiom.attributes import integer
from axiom.substore import SubStore
from axiom.dependency import installOn

from nevow.athena import LiveFragment
from nevow import rend
from nevow.rend import WovenContext
from nevow.testutil import FakeRequest
from nevow.inevow import IRequest, IResource

from xmantissa.ixmantissa import ITemplateNameResolver
from xmantissa import website, webapp
from xmantissa.webtheme import getAllThemes


class FakeResourceItem(Item):
    unused = integer()
    implements(IResource)

class WebIDLocationTest(TestCase):

    def setUp(self):
        store = Store(self.mktemp())
        ss = SubStore.createNew(store, ['test']).open()
        self.pa = webapp.PrivateApplication(store=ss)
        installOn(self.pa, ss)


    def test_powersUpTemplateNameResolver(self):
        """
        L{PrivateApplication} implements L{ITemplateNameResolver} and should
        power up the store it is installed on for that interface.
        """
        self.assertIn(
            self.pa,
            self.pa.store.powerupsFor(ITemplateNameResolver))


    def test_suchWebID(self):
        """
        Verify that retrieving a webID gives the correct resource.
        """
        i = FakeResourceItem(store=self.pa.store)
        wid = self.pa.toWebID(i)
        ctx = FakeRequest()
        self.assertEqual(self.pa.createResource().locateChild(ctx, [wid]),
                         (i, []))


    def test_noSuchWebID(self):
        """
        Verify that non-existent private URLs generate 'not found' responses.
        """
        ctx = FakeRequest()
        for segments in [
            # something that looks like a valid webID
            ['0000000000000000'],
            # something that doesn't
            ["nothing-here"],
            # more than one segment
            ["two", "segments"]]:
            self.assertEqual(self.pa.createResource().locateChild(ctx, segments),
                             rend.NotFound)


class TestFragment(LiveFragment):
    def locateChild(self, ctx, segs):
        if segs[0] == 'child-of-fragment':
            return ('I AM A CHILD OF THE FRAGMENT', segs[1:])
        return rend.NotFound


class TestClientFactory(object):
    """
    Dummy L{LivePageFactory}.

    @ivar magicSegment: The segment for which to return L{returnValue} from
    L{getClient}.
    @type magicSegment: C{str}

    @ivar returnValue: The value to return from L{getClient} when it is passed
    L{magicSegment}.
    @type returnValue: C{str}.
    """
    def __init__(self, magicSegment, returnValue):
        self.magicSegment = magicSegment
        self.returnValue = returnValue


    def getClient(self, seg):
        if seg == self.magicSegment:
            return self.returnValue


class GenericNavigationAthenaPageTests(TestCase):
    """
    Tests for L{GenericNavigationAthenaPage}.
    """

    def setUp(self):
        """
        Set up a site store, user store, and page instance to test with.
        """
        s = Store(self.mktemp())
        installOn(website.WebSite(store=s), s)
        s.parent = s

        ss = SubStore.createNew(s, ['child', 'lookup'])
        ss = ss.open()

        privapp = webapp.PrivateApplication(store=ss)
        installOn(privapp, ss)

        self.navpage = webapp.GenericNavigationAthenaPage(
            privapp,
            TestFragment(),
            privapp.getPageComponents())


    def test_childLookup(self):
        """
        L{GenericNavigationAthenaPage} should delegate to its fragment and its
        L{LivePageFactory} when it cannot find a child itself.
        """
        self.navpage.factory = tcf = TestClientFactory(
            'client-of-livepage', 'I AM A CLIENT OF THE LIVEPAGE')

        self.assertEqual(self.navpage.locateChild(None,
                                                 ('child-of-fragment',)),
                         ('I AM A CHILD OF THE FRAGMENT', ()))
        self.assertEqual(self.navpage.locateChild(None,
                                             (tcf.magicSegment,)),
                        (tcf.returnValue, ()))


    def test_jsModuleLocation(self):
        """
        L{GenericNavigationAthenaPage} should share its Athena JavaScript module
        location with all other pages that use L{xmantissa.cachejs}, and
        provide links to /__jsmodule__/.
        """
        ctx = WovenContext()
        req = FakeRequest()
        ctx.remember(req, IRequest)
        self.navpage.beforeRender(ctx)
        urlObj = self.navpage.getJSModuleURL('Mantissa')
        self.assertEqual(urlObj.pathList()[0], '__jsmodule__')
