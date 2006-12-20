
from twisted.web import microdom
from twisted.trial.unittest import TestCase
from twisted.python.reflect import qual

from nevow.athena import LivePage
from nevow.loaders import stan
from nevow.tags import (
    html, head, body, img, script, link, invisible, directive)
from nevow.context import WovenContext
from nevow.testutil import FakeRequest, AccumulatingFakeRequest as makeRequest
from nevow.flat import flatten
from nevow.inevow import IRequest
from nevow.page import renderer

from axiom.store import Store
from axiom.substore import SubStore
from axiom.dependency import installOn

from xmantissa.webtheme import (
    getAllThemes, getInstalledThemes, MantissaTheme, ThemedFragment,
    ThemedElement, _ThemedMixin)
from xmantissa.website import WebSite
from xmantissa.offering import installOffering
from xmantissa.plugins.baseoff import baseOffering

def testHead(theme):
    """
    Check that the head method of the given them doesn't explode.
    @param theme: probably an L{xmantissa.webtheme.XHTMLDirectoryTheme}
    """
    s = Store()
    flatten(theme.head(makeRequest(), WebSite(store=s, portNumber=80,
                                              securePortNumber=443)))

class WebThemeTestCase(TestCase):
    def _render(self, element):
        """
        Put the given L{IRenderer} provider into an L{athena.LivePage} and
        render it.  Return a Deferred which fires with the request object used
        which is an instance of L{nevow.testutil.FakeRequest}.
        """
        p = LivePage(
            docFactory=stan(
                html[
                    head(render=directive('liveglue')),
                    body[
                        invisible(render=lambda ctx, data: element)]]))
        element.setFragmentParent(p)

        ctx = WovenContext()
        req = FakeRequest()
        ctx.remember(req, IRequest)

        d = p.renderHTTP(ctx)
        def rendered(ign):
            p.action_close(None)
            return req
        d.addCallback(rendered)
        return d


    def test_getAllThemesPrioritization(self):
        """
        Test that the L{xmantissa.webtheme.getAllThemes} function returns
        L{ITemplateNameResolver} providers from the installed
        L{xmantissa.ixmantissa.IOffering} plugins in priority order.
        """
        lastPriority = None
        for theme in getAllThemes():
            if lastPriority is None:
                lastPriority = theme.priority
            else:
                self.failIf(
                    theme.priority > lastPriority,
                    "Theme out of order: %r" % (theme,))
                lastPriority = theme.priority


    def test_getInstalledThemes(self):
        """
        Test that only themes which belong to offerings installed on a
        particular store are returned by
        L{xmantissa.webtheme.getInstalledThemes}.
        """
        dbdir = self.mktemp()
        s = Store(dbdir)

        self.assertEquals(getInstalledThemes(s), [])

        installOffering(s, baseOffering, {})

        installedThemes = getInstalledThemes(s)
        self.assertEquals(len(installedThemes), 1)
        self.failUnless(isinstance(installedThemes[0], MantissaTheme))


    def _defaultThemedRendering(self, cls):
        class ThemedSubclass(cls):
            pass
        d = self._render(ThemedSubclass())
        def rendered(req):
            self.assertIn(
                qual(ThemedSubclass),
                req.v)
            self.assertIn(
                'specified no <code>fragmentName</code> attribute.',
                req.v)
        d.addCallback(rendered)
        return d


    def test_themedFragmentDefaultRendering(self):
        """
        Test that a ThemedFragment which does not override fragmentName is
        rendered with some debugging tips.
        """
        return self._defaultThemedRendering(ThemedFragment)


    def test_themedElementDefaultRendering(self):
        """
        Test that a ThemedElement which does not override fragmentName is
        rendered with some debugging tips.
        """
        return self._defaultThemedRendering(ThemedElement)


    def test_websiteDiscovery(self):
        """
        Test that L{_ThemedMixin.getWebSite} finds the right object whether it
        is wrapped around a user store or the store store.
        """
        s = Store(self.mktemp())
        installOn(WebSite(store=s, portNumber=80), s)

        ss = SubStore.createNew(s, ['user']).open()
        installOn(WebSite(store=ss, portNumber=8080), ss)

        themed = _ThemedMixin()
        themed.store = s
        self.assertEquals(
            themed.getWebSite().portNumber, 80,
            "Found the wrong WebSite from the site store.")

        themed = _ThemedMixin()
        themed.store = ss
        self.assertEquals(
            themed.getWebSite().portNumber, 80,
            "Found the wrong WebSite from the user store.")

    def test_imageSourceNotRewritten(self):
        """
        Test that an image tag which includes a hostname in its source does not
        have that source rewritten.
        """
        s = Store()
        installOn(WebSite(store=s, portNumber=80, hostname=u'example.com'), s)

        class TestElement(ThemedElement):
            docFactory = stan(img(src='http://example.org/Foo.png'))
            store = s

        d = self._render(TestElement())
        def rendered(req):
            dom = microdom.parseString(req.v)
            img = dom.getElementsByTagName('img')[0]
            self.assertEquals("http://example.org/Foo.png",
                              img.getAttribute('src'))
        d.addCallback(rendered)
        return d


    def _mutate(self, urlString):
        return "%s_mutated" % (urlString,)


    def test_originalImageRendererRespected(self):
        """
        Test that an image tag with a render directive has that directive
        invoked after the URL has been rewritten.
        """
        s = Store()
        installOn(WebSite(store=s, portNumber=80, hostname=u'example.com'), s)

        class TestElement(ThemedElement):
            docFactory = stan(img(src='/Foo.png', render=directive('mutate')))
            store = s

            def mutate(this, request, tag):
                this.mutated = self._mutate(tag.attributes['src'])
                return tag
            renderer(mutate)

        ele = TestElement()
        d = self._render(ele)
        def rendered(req):
            self.assertEquals(ele.mutated, self._mutate('/Foo.png'))
        d.addCallback(rendered)
        return d


    def test_scriptSourceNotRewritten(self):
        """
        Test that a script tag which includes a hostname in its source does not
        have that source rewritten.
        """
        s = Store()
        installOn(WebSite(store=s, portNumber=80, hostname=u'example.com'), s)

        class TestElement(ThemedElement):
            docFactory = stan(script(src='http://example.org/Foo.js'))
            store = s

        d = self._render(TestElement())
        def rendered(req):
            self.assertIn(
                '<script src="http://example.org/Foo.js"></script>',
                req.v)
        d.addCallback(rendered)
        return d


    def test_originalScriptRendererRespected(self):
        """
        Test that an script tag with a render directive has that directive
        invoked after the URL has been rewritten.
        """
        s = Store()
        installOn(WebSite(store=s, portNumber=80, hostname=u'example.com'), s)

        class TestElement(ThemedElement):
            docFactory = stan(script(src='/Foo.js', render=directive('mutate')))
            store = s

            def mutate(this, request, tag):
                this.mutated = self._mutate(tag.attributes['src'])
                return tag
            renderer(mutate)

        ele = TestElement()
        d = self._render(ele)
        def rendered(req):
            self.assertEquals(ele.mutated, self._mutate('/Foo.js'))
        d.addCallback(rendered)
        return d

    def test_linkHypertextReferenceNotRewritten(self):
        """
        Test that a link which includes a hostname in its href does not have
        that href rewritten.
        """
        s = Store()
        installOn(WebSite(store=s, portNumber=80, hostname=u'example.com'), s)

        class TestElement(ThemedElement):
            docFactory = stan(link(href='http://example.org/Foo.css'))
            store = s

        d = self._render(TestElement())
        def rendered(req):
            self.assertIn(
                '<link href="http://example.org/Foo.css" />',
                req.v)
        d.addCallback(rendered)
        return d


    def test_originalLinkRendererRespected(self):
        """
        Test that a link tag with a render directive has that directive invoked
        after the URL has been rewritten.
        """
        s = Store()
        installOn(WebSite(store=s, portNumber=80, hostname=u'example.com'), s)

        class TestElement(ThemedElement):
            docFactory = stan(link(href='/Foo.css', render=directive('mutate')))
            store = s

            def mutate(this, request, tag):
                this.mutated = self._mutate(tag.attributes['href'])
                return tag
            renderer(mutate)

        ele = TestElement()
        d = self._render(ele)
        def rendered(req):
            self.assertEquals(ele.mutated, self._mutate('/Foo.css'))
        d.addCallback(rendered)
        return d

    def test_head(self):
        testHead(MantissaTheme(''))
