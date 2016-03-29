# LanguageTool.py
#
# This is a simple Sublime Text plugin for checking grammar. It passes buffer
# content to LanguageTool (via http) and highlights reported problems.

import sublime, sublime_plugin
import xml.etree.ElementTree
import urllib

# problems is an array of n-tuples in the form
# (x0, x1, msg, description, suggestions, regionID, orgContent)
problems = []

# select characters with indices [i, j]
def moveCaret(view, i, j):
	target = view.text_point(0, i)
	view.sel().clear()
	view.sel().add(sublime.Region(target, target+j-i))

# returns key of region i
def getProbKey(i):
	return "p" + str(i)

# wrapper
def msg(str):
	sublime.status_message(str)

def clearProblems(v):
	global problems
	for i in range(0, len(problems)):
		v.erase_regions(getProbKey(i))
	problems = []

def selectProblem(v, p):
	r = v.get_regions(p[5])[0]
	moveCaret(v, r.a, r.b)
	v.show_at_center(r)
	if len(p[4])>0:
		msg(u"{0} ({1})".format(p[3], p[4]))
	else:
		msg(p[3])
	printProblem(p)

def problemSolved(v, p):
	rl = v.get_regions(p[5])
	if len(rl) == 0:
		print('tried to find non-existing region with key ' + p[5])
		return True
	r = rl[0]
	# a problem is solved when either:
	# 1. its region has zero length
	# 2. its contents have been changed
	return r.empty() or (v.substr(r) != p[6])

# navigation function
class gotoNextLanguageProblemCommand(sublime_plugin.TextCommand):
	def run(self, edit, jumpForward = True):
		global problems
		v = self.view
		if len(problems) > 0:
			sel = v.sel()[0]
			if jumpForward:
				for p in problems:
					r = v.get_regions(p[5])[0];
					if (not problemSolved(v, p)) and (sel.begin() < r.a):
						selectProblem(v, p)
						return
			else:
				for p in reversed(problems):
					r = v.get_regions(p[5])[0];
					if (not problemSolved(v, p)) and (r.a < sel.begin()):
						selectProblem(v, p)
						return
		msg("no further language problems to fix")

def onSuggestionListSelect(v, edit, p, suggestions, choice):
	global problems
	if choice != -1:
		r = v.get_regions(p[5])[0]
		v.replace(edit, r, suggestions[choice])
		c = r.a + len(suggestions[choice])
		moveCaret(v, c, c) # move caret to end of region
		v.run_command("goto_next_language_problem")
	else:
		selectProblem(v, p)

class markLanguageProblemSolvedCommand(sublime_plugin.TextCommand):
	def run(self, edit, applyFix):
		global problems
		v = self.view
		sel = v.sel()[0]
		for p in problems:
			r = v.get_regions(p[5])[0]
			nextCaretPos = r.a;
			if r == sel:
				if applyFix and (len(p[4])>0):
					# fix selected problem:
					if '#' in p[4]:
						# there are multiple suggestions
						suggestions = p[4].split('#')
						callbackF = lambda i : onSuggestionListSelect(v, edit, p, suggestions, i)
						v.window().show_quick_panel(suggestions, callbackF)
						return
					else:
						# there is a single suggestion
						v.replace(edit, r, p[4])
						nextCaretPos = r.a + len(p[4])
				else:

					# ignore problem:
					if p[2] == "Possible Typo":
						# if this is a typo then include all identical typos in the
						# list of problems to be fixed
						pID = lambda py : (py[2], py[6]) # (msg, orgContent)
						ignoreProbs = [px for px in problems if pID(p)==pID(px)]
					else:
						# otherwise select just this one problem
						ignoreProbs = [p]

					for p2 in ignoreProbs:
						ignoreProblem(p2, v, self, edit)

				# after either fixing or ignoring:
				moveCaret(v, nextCaretPos, nextCaretPos) # move caret to end of region
				v.run_command("goto_next_language_problem")
				return

		# if no problems are selected:
		msg('no language problem selected')

def ignoreProblem(p, v, self, edit):
	# dummy edit to enable undoing ignore
	r = v.get_regions(p[5])[0]
	v.insert(edit, v.size(), "")
	# change region associated with this problem to a 0-length region
	dummyRg = sublime.Region(r.a, r.a)
	v.add_regions(p[5], [dummyRg], "string", "", sublime.DRAW_OUTLINED)

class LanguageToolCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		global problems
		v = self.view
		clearProblems(v)
		settings = sublime.load_settings("LanguageTool.sublime-settings")
		server = settings.get('languagetool_server', 'https://languagetool.org:8081/')
		strText = v.substr(sublime.Region(0, v.size()))
		data = urllib.urlencode({'language' : 'en-GB', 'text': strText.encode('utf8')})
		try:
			content = urllib.urlopen(server, data).read()
			root = xml.etree.ElementTree.fromstring(content)
		except IOError:
			msg('error, unable to connect via http, is LanguageTool running?')
		except xml.parsers.expat.ExpatError:
			msg('could not parse server response (may be due to quota if using http://languagetool.org)')
		else:
			ind = 0;
			fields_int = ["fromx", "fromy", "tox", "toy"]
			fields_str = ["category", "msg", "replacements"]
			for child in root:
				if child.tag == "error":
					ax, ay, bx, by = [int(child.attrib[x]) for x in fields_int]
					category, message, replacements = [child.attrib[x] for x in fields_str]
					a = v.text_point(ay, ax);
					b = v.text_point(by, bx);
					region = sublime.Region(a, b)
					regionKey = getProbKey(ind)
					v.add_regions(regionKey, [region], "string", "", sublime.DRAW_OUTLINED)
					orgContent = v.substr(region)
					p = (a, b, category, message, replacements, regionKey, orgContent)
					problems.append(p)
					printProblem(p)
					ind += 1
			if ind>0:
				selectProblem(v, problems[0])
			else:
				msg("no language problems were found :-)")

# used for debugging
def printProblem(p):
	return
	a = str(p[0])
	b = str(p[1])
	print("%4s -> %4s : %-10s (%s)" % (a, b, p[6], p[3]))

class LanguageToolListener(sublime_plugin.EventListener):
	def on_modified(self, view):
		# buffer text was changed, recompute region highlights
		for p in problems:
			rL = view.get_regions(p[5])
			if len(rL) > 0:
				regionScope = "" if problemSolved(view, p) else "string"
				view.add_regions(p[5], rL, regionScope, "",  sublime.DRAW_OUTLINED)
