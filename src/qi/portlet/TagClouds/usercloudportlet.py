from time import time
from operator import itemgetter
from zope.interface import implements
from zope import schema
from zope.formlib import form
from zope.i18n import translate
from zope.component import getMultiAdapter

from plone.portlets.interfaces import IPortletDataProvider
from plone.app.portlets.portlets import base
from plone.memoize import ram

from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from Products.CMFCore.utils import getToolByName
from Products.PythonScripts.standard import url_quote

from qi.portlet.TagClouds import TagCloudPortletMessageFactory as _


def _cachekey(method, self):
    """Time, language, settings based cache
    XXX: If you need to publish private items you should probably
    include the member id in the cache key.
    """
    portal_state = getMultiAdapter((self.context, self.request),
        name=u'plone_portal_state')
    portal_url = portal_state.portal_url()
    lang = self.request.get('LANGUAGE', 'en')
    return hash((portal_url, lang, self.data,
                 time() // self.data.refreshInterval))


class IUserCloudPortlet(IPortletDataProvider):

    portletTitle = schema.TextLine(
        title = _(u"Portlet title"),
        description = _(u"The title of the tagcloud."),
        required = True,
        default = u"User Cloud")

    levels = schema.Int(
        title = _(u"Number of different sizes"),
        description = _(u"This number will also determine the biggest size."),
        required = True,
        min = 1,
        max = 6,
        default = 5)

    count = schema.Int(
        title = _(u"Maximum number of shown tags."),
        description = _(u"If greater than zero this number will limit the " \
        "tags shown."),
        required = True,
        min = 0,
        default = 30)

    refreshInterval = schema.Int(
        title = _(u"Refresh interval"),
        description = _(u"The maximum time in seconds for which the portal"\
            " will cache the results. Be careful not to use low values."),
        required = True,
        min = 1,
        default = 3600,
        )


class Assignment(base.Assignment):
    """
    """

    implements(IUserCloudPortlet)

    def __init__(self, portletTitle="UserCloud", levels=5,
        count=0, refreshInterval=3600):

        self.portletTitle = portletTitle
        self.levels = levels
        self.count = count
        self.refreshInterval = refreshInterval

    @property
    def title(self): return "User Cloud portlet"


class Renderer(base.Renderer):
    render = ViewPageTemplateFile('tagcloudportlet.pt')

    def __init__(self, context, request, view, manager, data):
        super(Renderer, self).__init__(context, request, view, manager, data)
        self.portal_url = getToolByName(context, 'portal_url')()
        self.catalog = getToolByName(context, 'portal_catalog')
        self.putils = getToolByName(context, 'plone_utils')
        self.levels = data.levels
        self.count = data.count

    @ram.cache(_cachekey)
    def getTags(self):
        tagOccs = self.getTagOccurrences()
        # If count has been set sort by occurences and keep the "count" first

        if self.count:
            sortedOccs = sorted(tagOccs.items(),
                                key=itemgetter(1),
                                reverse=True)[:self.count]
            tagOccs = dict(sortedOccs)

        thresholds = self.getThresholds(tagOccs.values())
        tags = list(tagOccs.keys())
        tags.sort()
        res = []
        for tag in tags:
            d = {}
            size = self.getTagSize(tagOccs[tag], thresholds)
            if size == 0:
                continue
            d["text"] = tag
            d["class"] = "cloud" + str(size)
            href= self.portal_url + \
                "/posts?users="+url_quote(tag)
            d["href"]=href
            d["count"] = translate(
                _(u'${count} items', mapping={'count': tagOccs[tag]}),
                context=self.request)
            res.append(d)
        return res

    def getPortletTitle(self):
        return self.data.portletTitle

    def getSearchSubjects(self):
        result = list(self.catalog.uniqueValuesFor('user'))
        return result

    def getTagOccurrences(self):
        tags = self.getSearchSubjects()
        tagOccs = {}
        query = {}
        query['portal_type'] = 'g24.elements.basetype'
        for tag in tags:
            result = []
            query['user'] = tag
            result = self.catalog.searchResults(**query)
            if result:
                tagOccs[tag] = len(result)

        return tagOccs

    def getTagSize(self, tagWeight, thresholds):
        size = 0
        if tagWeight:
            for t in thresholds:
                size += 1
                if tagWeight <= t:
                    break
        return size

    def getThresholds(self, sizes):
        """This algorithm was taken from Anders Pearson's blog:
         http://thraxil.com/users/anders/posts/2005/12/13/scaling-tag-clouds/
        """
        if not sizes:
            return [1 for i in range(0, self.levels)]
        minimum = min(sizes)
        maximum = max(sizes)
        return [pow(maximum - minimum + 1, float(i) / float(self.levels))
            for i in range(0, self.levels)]

    @property
    def available(self):
        return self.getSearchSubjects()


class AddForm(base.AddForm):
    form_fields = form.Fields(IUserCloudPortlet)

    def create(self, data):
        return Assignment(**data)


class EditForm(base.EditForm):
    form_fields = form.Fields(IUserCloudPortlet)
