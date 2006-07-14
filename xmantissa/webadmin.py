# -*- test-case-name: xmantissa.test.test_admin -*-

import operator, random, string, time

from zope.interface import implements

from twisted.python.components import registerAdapter
from twisted.python.util import sibpath
from twisted.python import log
from twisted.application.service import IService, Service
from twisted.conch import manhole
from twisted.cred.portal import IRealm

from nevow.page import renderer
from nevow.athena import expose

from epsilon import extime

from axiom.attributes import integer, boolean, timestamp, bytes, reference, inmemory, AND, OR
from axiom.item import Item
from axiom import userbase
from axiom.batch import BatchManholePowerup

from xmantissa import webtheme, liveform, webnav, tdb, tdbview, offering, signup, stats
from xmantissa.webapp import PrivateApplication
from xmantissa.website import WebSite, PrefixURLMixin
from xmantissa.ixmantissa import INavigableElement, INavigableFragment, \
    ISessionlessSiteRootPlugin
from xmantissa.plugins.baseoff import baseOffering

from nevow import rend, athena, static, tags as T


class DeveloperSite(Item, PrefixURLMixin):
    """Provides static content sessionlessly for the developer application.
    """
    implements(ISessionlessSiteRootPlugin)

    typeName = 'developer_site'
    schemaVersion = 1

    prefixURL = 'static/webadmin'

    # Counts of each kind of user
    developers = integer(default=0)
    administrators = integer(default=0)

    def installOn(self, other):
        other.powerUp(self, ISessionlessSiteRootPlugin)

    def createResource(self):
        return static.File(sibpath(__file__, 'static'))

class ParentCounterMixin:
    def _getDevSite(self):
        # Developer site is required.  Make one if there isn't one.
        # Make sure site-wide dependency is available
        for devsite in self.store.parent.query(DeveloperSite):
            break
        else:
            devsite = DeveloperSite(store=self.store.parent)
            devsite.installOn(self.store.parent)
        return devsite

    # XXX WAaah.  self.store.parent is None sometimes, depending on
    # how we got opened :/
    def increment(self):
#         devsite = self._getDevSite()
#         setattr(devsite, self.counterAttribute, getattr(devsite, self.counterAttribute) + 1)
        pass

    def decrement(self):
#         devsite = self._getDevSite()
#         setattr(devsite, self.counterAttribute, getattr(devsite, self.counterAttribute) - 1)
        pass

class AdminStatsApplication(Item, ParentCounterMixin):
    """
    """
    implements(INavigableElement)

    schemaVersion = 1
    typeName = 'administrator_application'

    counterAttribute = 'administrators'

    updateInterval = integer(default=5)

    def installOn(self, other):
        self.increment()
        other.powerUp(self, INavigableElement)

    def deletedFromStore(self, *a, **kw):
        self.decrement()
        return super(AdminStatsApplication, self).deletedFromStore(*a, **kw)

    def getTabs(self):
        return [webnav.Tab('Admin', self.storeID, 0.0,
                           [webnav.Tab('Stats', self.storeID, 0.1)],
                           authoritative=False)]


class LocalUserBrowser(Item):
    """
    XXX I am an unfortunate necessity.

    This class shouldn't exist, and in fact, will be destroyed at the first
    possible moment.  It's stateless, existing only to serve as a web lookup
    hook for the UserInteractionFragment view class.
    """

    implements(INavigableElement)

    typeName = 'local_user_browser'
    schemaVersion = 1

    garbage = integer(default=12345678653)

    def installOn(self, other):
        other.powerUp(self, INavigableElement)

    def getTabs(self):
        return [webnav.Tab('Admin', self.storeID, 0.0,
                           [webnav.Tab('Local Users', self.storeID, 0.1)],
                           authoritative=False)]



class UserInteractionFragment(webtheme.ThemedElement):
    """
    Contains two other user-interface elements which allow existing users to be
    browsed and new users to be created, respectively.
    """
    fragmentName = 'admin-user-interaction'

    def __init__(self, userBrowser):
        """
        @param userBrowser: a LocalUserBrowser instance
        """
        super(UserInteractionFragment, self).__init__()
        self.browser = userBrowser


    def userBrowser(self, request, tag):
        """
        Render a TDB of local users.
        """
        f = LocalUserBrowserFragment(self.browser)
        f.docFactory = webtheme.getLoader(f.fragmentName)
        f.setFragmentParent(self)
        return f
    renderer(userBrowser)


    def userCreate(self, request, tag):
        """
        Render a form for creating new users.
        """
        userCreator = liveform.LiveForm(
            self.createUser,
            [liveform.Parameter(
                    "localpart",
                    liveform.TEXT_INPUT,
                    unicode,
                    "localpart"),
             liveform.Parameter(
                    "domain",
                    liveform.TEXT_INPUT,
                    unicode,
                    "domain"),
             liveform.Parameter(
                    "password",
                    liveform.PASSWORD_INPUT,
                    unicode,
                    "password")])
        userCreator.setFragmentParent(self)
        return userCreator
    renderer(userCreate)


    def createUser(self, localpart, domain, password=None):
        """
        Create a new, blank user account with the given name and domain and, if
        specified, with the given password.

        @type localpart: C{unicode}
        @param localpart: The local portion of the username.  ie, the
        C{'alice'} in C{'alice@example.com'}.

        @type domain: C{unicode}
        @param domain: The domain portion of the username.  ie, the
        C{'example.com'} in C{'alice@example.com'}.

        @type password: C{unicode} or C{None}
        @param password: The password to associate with the new account.  If
        C{None}, generate a new password automatically.
        """
        loginSystem = self.browser.store.parent.findUnique(userbase.LoginSystem)
        if password is None:
            password = u''.join([random.choice(string.ascii_letters + string.digits) for i in xrange(8)])
        loginSystem.addAccount(localpart, domain, password)

registerAdapter(UserInteractionFragment, LocalUserBrowser, INavigableFragment)



class _EndowDepriveActionBase(tdbview.Action):
    clickFmt = ("return Nevow.Athena.Widget.get(this"
                ").updateUserDetail(this, %d, event, %r);")

    def toLinkStan(self, idx, loginMethod):
        return T.a(href='#',
                   style="padding-right: 5px;",
                   onclick=self.clickFmt % (idx, self.benefactorAction))[
            self.benefactorAction]

    def actionable(self, item):
        return True



class EndowAction(_EndowDepriveActionBase):
    benefactorAction = 'endow'



class DepriveAction(_EndowDepriveActionBase):
    benefactorAction = 'deprive'


class DateOrUnknownColumnView(tdbview.DateColumnView):

    def stanFromValue(self, idx, item, value):
        if value is None:
            return 'Unknown'
        else:
            return value.asHumanly()

class LocalUserBrowserFragment(tdbview.TabularDataView):
    jsClass = u'Mantissa.Admin.LocalUserBrowser'

    def __init__(self, userBrowser):
        tdm = tdb.TabularDataModel(
            userBrowser.store.parent,
            userbase.LoginMethod,
            [userbase.LoginMethod.localpart,
             userbase.LoginMethod.domain,
             userbase.LoginMethod.verified,
             userbase.LoginMethod.lastActivity],
            baseComparison=(userbase.LoginMethod.domain != None),
            defaultSortColumn='domain', # XXX TODO (domain, localpart) sorting
            defaultSortAscending=True)
        views = [
            tdbview.ColumnViewBase('localpart', typeHint='text'),
            tdbview.ColumnViewBase('domain', typeHint='text'),
            tdbview.ColumnViewBase('verified', typeHint='boolean'),
            DateOrUnknownColumnView('lastActivity')]

        actions = [
            EndowAction('Endow', None, None),
            DepriveAction('Deprive', None, None),
            ]
        super(LocalUserBrowserFragment, self).__init__(tdm, views, actions)

    def getActionFragment(self, targetID, action):
        loginMethod = self.itemFromTargetID(targetID)
        loginAccount = loginMethod.account
        return EndowDepriveFragment(
            self,
            loginMethod.localpart + u'@' + loginMethod.domain,
            loginAccount,
            action)
    expose(getActionFragment)


class EndowDepriveFragment(webtheme.ThemedElement):
    fragmentName = 'user-detail'

    def __init__(self, fragmentParent, username, loginAccount, which):
        super(EndowDepriveFragment, self).__init__(fragmentParent)
        self.account = loginAccount
        self.benefactors = list(self.account.store.query(signup.Multifactor))
        self.which = which
        self.username = username


    def _endow(self, **kw):
        subs = self.account.avatars.open()
        def endowall():
            for benefactor in kw.values():
                if benefactor is not None:
                    getattr(benefactor, self.which)(None, subs)
        subs.transact(endowall)


    def benefactorForm(self, request, tag):
        """
        Render a L{liveform.LiveForm} -- the main purpose of this fragment --
        which will allow the administrator to endow or deprive existing users
        using multifactors, which can be created through the signup mechanism
        interface.
        """

        def makeRemover(i):
            def remover(s3lected):
                if s3lected:
                    return self.benefactors[i]
                return None
            return remover

        f = liveform.LiveForm(
            self._endow,
            [liveform.Parameter(
                    'benefactors' + str(i),
                    liveform.FORM_INPUT,
                    liveform.LiveForm(
                        makeRemover(i),
                        [liveform.Parameter(
                                's3lected',
                                liveform.RADIO_INPUT,
                                bool,
                                b.briefMultifactorDescription(),
                                )],
                        '',
                        ),
                    )
             for (i, b)
             in enumerate(self.benefactors)],
            self.which.capitalize() + u' ' + self.username)
        f.setFragmentParent(self)
        return f
    renderer(benefactorForm)



class AdminStatsFragment(athena.LiveElement):
    implements(INavigableFragment)

    live = 'athena'
    jsClass = u'Mantissa.StatGraph.StatGraph'
    fragmentName = 'admin-stats'

    def __init__(self, *a, **kw):
        athena.LiveElement.__init__(self, *a, **kw)
        self.svc = None
        self.piePeriod = 60
        self.activeStats = []
        self.queryStats = None
    def _initializeObserver(self):
        "Look up the StatsService and registers to receive notifications of recorded stats."

        if self.svc:
            return
        m = IRealm(self.original.store.parent).accountByAddress(u"mantissa", None)
        if m:
            s = m.avatars.open()
            self.svc = s.findUnique(stats.StatsService)
            self.svc.addStatsObserver(self)
        else:
            self.svc = None
        self._seenStats = []
        self.page.notifyOnDisconnect().addCallback(
            lambda x: self.svc.removeStatsObserver(self))

    def fetchLastHour(self, name):
        """Retrieve the last 60 minutes of data points for the named stat."""
        end = self.svc.currentMinuteBucket
        beginning = end - 60
        if beginning < 0:
            beginning += stats.MAX_MINUTES
            # this is a round-robin list, so make sure to get
            # the part recorded before the wraparound:
            bs = self.svc.store.query(stats.StatBucket,
                                       AND(stats.StatBucket.type==unicode(name),
                                           stats.StatBucket.interval== u"minute",
                                           OR(stats.StatBucket.index >= beginning,
                                              stats.StatBucket.index <= end)))

        else:
            bs = self.svc.store.query(stats.StatBucket,
                                      AND(stats.StatBucket.type==unicode(name),
                                          stats.StatBucket.interval== u"minute",
                                          stats.StatBucket.index >= beginning,
                                          stats.StatBucket.index <= end))
        return zip(*[(unicode(b.time and b.time.asHumanly() or ''), b.value) for b in bs]) or [(), ()]



    def getGraphNames(self):
        self._initializeObserver()
        if not self.svc:
            return []
        return [(unicode(name), unicode(stats.statDescriptions[name])) for name in self.svc.statTypes]
    expose(getGraphNames)


    def addStat(self, name):
        data = self.fetchLastHour(name)
        self.activeStats.append(name)
        return data
    expose(addStat)


    def removeStat(self, name):
        self.activeStats.remove(name)
    expose(removeStat)


    def setPiePeriod(self, period):
        "Set how much time the query-time pie chart should cover."
        self.piePeriod = int(period)
    expose(setPiePeriod)


    def buildPie(self):
        "Called from javascript to produce the initial state of the query-time pie chart."
        self._initializeObserver()
        if not self.svc:
            return []

        data = []
        end = self.svc.currentMinuteBucket
        beginning = end - self.piePeriod
        if beginning < 0:
            beginning += stats.MAX_MINUTES
            # this is a round-robin list, so make sure to get
            # the part recorded before the wraparound:
            bs = self.svc.store.query(stats.QueryStatBucket, AND(
                                           stats.QueryStatBucket.interval== u"minute",
                                           OR(stats.QueryStatBucket.index >= beginning,
                                              stats.QueryStatBucket.index <= end)))

        else:
            bs = self.svc.store.query(stats.QueryStatBucket, AND(
                                          stats.QueryStatBucket.interval== u"minute",
                                          stats.QueryStatBucket.index >= beginning,
                                          stats.QueryStatBucket.index <= end))
        slices = {}
        start = time.time()
        for bucket in bs:
            slices.setdefault(bucket.type, []).append(bucket.value)
        log.msg("Query-stats query time: %s Items: %s" % (time.time() - start, bs.count()))
        for k, v in slices.items():
            tot =  sum(v)
            if tot:
                slices[k] = tot
            else:
                del slices[k]

        self.queryStats = slices
        return self.pieSlices()
    expose(buildPie)

    def pieSlices(self):
        data = self.queryStats.items()
        data.sort(key=operator.itemgetter(1), reverse=True)
        return zip(*data)

    def queryStatUpdate(self, time, updates):
        if self.queryStats is None:
            return
        for k, delta in updates:
            val = self.queryStats.get(k, 0)
            self.queryStats[k] = val + delta
        pie = self.pieSlices()
        self.callRemote('updatePie', pie).addErrback(log.err)

    def statUpdate(self, time, updates):
        "Update the graphs with the new data point."
        data = []
        for name, value in updates:
            if name.startswith('_'):
                #not a directly graphable stat
                continue
            if name in self.activeStats:
                data.append((unicode(name), value))
        self.callRemote('update', unicode(time.asHumanly()), dict(data))



    def head(self):
        # XXX TODO - There is a race condition loading new dependencies after
        # the initial page render.  Work around this by forcing all these
        # dependencies to load at startup.
        return [
            T.script(language='javascript', src='/private/jsmodule/PlotKit.' + x)
            for x in ['Base', 'Canvas', 'Layout', 'SVGRenderer', 'SweetSVG', 'Canvas', 'SweetCanvas']]

    def _query(self, *a, **kw):
        return self.original.store.parent.query(*a, **kw)

    def loginCount(self, request, tag):
        for ls in self._query(userbase.LoginSystem):
            return ls.loginCount
    renderer(loginCount)


    def failedLoginCount(self, request, tag):
        for ls in self._query(userbase.LoginSystem):
            return ls.failedLogins
    renderer(failedLoginCount)


    def userCount(self, request, tag):
        count = 0
        for la in self._query(userbase.LoginAccount):
            count += 1
        return count
    renderer(userCount)


    def disabledUserCount(self, request, tag):
        count = 0
        for la in self._query(userbase.LoginAccount, userbase.LoginAccount.disabled != 0):
            count += 1
        return count
    renderer(disabledUserCount)


    def developerCount(self, request, tag):
        for ds in self._query(DeveloperSite):
            return ds.developers
    renderer(developerCount)


    def administratorCount(self, request, tag):
        for ds in self._query(DeveloperSite):
            return ds.administrators
    renderer(administratorCount)

registerAdapter(AdminStatsFragment, AdminStatsApplication, INavigableFragment)


class DeveloperApplication(Item, ParentCounterMixin):
    """
    """
    implements(INavigableElement)

    counterAttribute = 'developers'

    schemaVersion = 1
    typeName = 'developer_application'

    statementCount = integer(default=0)

    def installOn(self, other):
        self.increment()
        other.powerUp(self, INavigableElement)

    def deletedFromStore(self, *a, **kw):
        self.decrement()
        return super(DeveloperApplication, self).deletedFromStore(*a, **kw)

    # INavigableElement
    def getTabs(self):
        return [webnav.Tab('Admin', self.storeID, 0.0,
                           [webnav.Tab('REPL', self.storeID, 0.0)],
                           authoritative=False)]

class REPL(athena.LiveFragment):
    """
    Provides an interactive Read-Eval-Print loop. On a web page (duh).
    """
    implements(INavigableFragment)

    jsClass = u'Mantissa.InterpreterWidget'

    fragmentName = 'admin-python-repl'
    live = 'athena'

    def __init__(self, *a, **kw):
        rend.Fragment.__init__(self, *a, **kw)
        self.namespace = {'s': self.original.store, 'getStore': self.getStore}
        self.interpreter = manhole.ManholeInterpreter(
            self,
            self.namespace)

    def getStore(self, name, domain):
        """Convenience method for the REPL. I got tired of typing this string every time I logged in."""
        return IRealm(self.original.store.parent).accountByAddress(name, domain).avatars.open()

    def head(self):
        return ()


    def addOutput(self, output, async=False):
        self.callRemote('addOutputLine', unicode(output, 'ascii'))


    def evaluateInputLine(self, inputLine):
        return self.interpreter.push(inputLine)
    expose(evaluateInputLine)



registerAdapter(REPL, DeveloperApplication, INavigableFragment)

class Traceback(Item):
    typeName = 'mantissa_traceback'
    schemaVersion = 1

    when = timestamp()
    traceback = bytes()
    collector = reference()

    def __init__(self, store, collector, failure):
        when = extime.Time()
        traceback = failure.getTraceback()
        super(Traceback, self).__init__(
            store=store,
            traceback=traceback,
            when=when,
            collector=collector)

class TracebackCollector(Item, Service):
    implements(IService)

    typeName = 'mantissa_traceback_collector'
    schemaVersion = 1

    tracebackCount = integer(default=0)

    parent = inmemory()
    running = inmemory()
    name = inmemory()

    def installOn(self, other):
        other.powerUp(self, IService)
        self.setServiceParent(other)

    def startService(self):
        log.addObserver(self.emit)

    def stopService(self):
        log.removeObserver(self.emit)

    def emit(self, event):
        if event.get('isError') and event.get('failure') is not None:
            f = event['failure']
            def txn():
                self.tracebackCount += 1
                Traceback(store=self.store, collector=self, failure=f)
            self.store.transact(txn)

    def getTracebacks(self):
        """
        Return an iterable of Tracebacks that have been collected.
        """
        return self.store.query(Traceback,
                                Traceback.collector == self)


class TracebackViewer(Item):
    implements(INavigableElement)

    typeName = 'mantissa_tb_viewer'
    schemaVersion = 1

    allowDeletion = boolean(default=False)

    def installOn(self, other):
        other.powerUp(self, INavigableElement)

    def getTabs(self):
        return [webnav.Tab('Admin', self.storeID, 0.0,
                           [webnav.Tab('Errors', self.storeID, 0.3)],
                           authoritative=False)]

    def _getCollector(self):
        def ifCreate(coll):
            coll.installOn(self.store.parent)
        return self.store.parent.findOrCreate(TracebackCollector, ifCreate)

    # this needs to be moved somewhere else, topPanelContent is no more
    #def topPanelContent(self):
    #    # XXX There should really be a juice protocol for this.
    #    return '%d errors logged' % (self._getCollector().tracebackCount,)


class TracebackViewerFragment(rend.Fragment):
    implements(INavigableFragment)

    live = False
    fragmentName = 'traceback-viewer'

    def head(self):
        return ()

    def render_tracebacks(self, ctx, data):
        for tb in self.original._getCollector().getTracebacks():
            yield T.div[T.code[T.pre[tb.traceback]]]

registerAdapter(TracebackViewerFragment, TracebackViewer, INavigableFragment)


class DONTUSETHISBenefactor(Item):
    typeName = 'seriously_dont_use_it_is_just_an_example'
    schemaVersion = 1

    didYouUseIt = integer(default=0)

    def endow(self, ticket, avatar):
        self.didYouUseIt += 1 # OMFG can you *read*??
        for X in WebSite, PrivateApplication, DeveloperApplication, TracebackViewer:
            X(store=avatar).installOn(avatar)

# This is a lot like the above benefactor.  We should probably delete
# the above benefactor now.
class AdministrativeBenefactor(Item):
    typeName = 'mantissa_administrative_benefactor'
    schemaVersion = 1

    endowed = integer(default=0)

    def endow(self, ticket, avatar):
        self.endowed += 1
        for powerUp in [

            # Install a web site for the individual user as well.
            # This is necessary because although we have a top-level
            # website for everybody, not all users should be allowed
            # to log in through the web (like UNIX's "system users",
            # "nobody", "database", etc.)  Note, however, that there
            # is no port number, because the WebSite's job in this
            # case is to be a web *resource*, not a web *server*.
            WebSite,

            # Now we install the 'private application' plugin for
            # 'admin', on admin's private store, This provides the URL
            # "/private", but only when 'admin' is logged in.  It is a
            # hook to hang other applications on.  (XXX Rename:
            # PrivateApplication should probably be called
            # PrivateAppShell)
            PrivateApplication,

            # These are plugins *for* the PrivateApplication; they
            # publish objects via the tab-based navigation: a
            # statistics page and a Python interactive interpreter,
            # respectively.
            AdminStatsApplication,
            DeveloperApplication,

            # And another one: SignupConfiguration allows the
            # administrator to add signup forms which grant various
            # kinds of account.
            signup.SignupConfiguration,

            # This one lets the administrator view unhandled
            # exceptions which occur in the server.
            TracebackViewer,

            # This one lets the administrator ssh in to a REPL in the
            # batch process.
            BatchManholePowerup,

            # And this one gives the administrator a page listing all
            # users which exist in this site's credentials database.
            LocalUserBrowser]:


            avatar.findOrCreate(powerUp).installOn(avatar)

        # This is another PrivateApplication plugin.  It allows
        # the administrator to configure the services offered
        # here.
        oc = avatar.findOrCreate(offering.OfferingConfiguration)
        oc.installOn(avatar)

        installedOffering = avatar.parent.findUnique(
                                offering.InstalledOffering,
                                offering.InstalledOffering.offeringName == baseOffering.name,
                                default=None)

        if installedOffering is None:
            oc.installOffering(baseOffering, None)

    def deprive(self, ticket, avatar):
        # Only delete the really administratory things.
        for powerUp in [
            AdminStatsApplication, DeveloperApplication,
            TracebackViewer, LocalUserBrowser]:
            avatar.findUnique(powerUp).deleteFromStore()
