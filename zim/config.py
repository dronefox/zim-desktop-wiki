# -*- coding: utf8 -*-

# Copyright 2009 Jaap Karssenberg <pardus@cpan.org>

'''FIXME'''

import sys
import os
import re
import logging

from zim.fs import *
from zim.parsing import TextBuffer, ParsingError

logger = logging.getLogger('zim.config')

ZIM_DATA_DIR = None
XDG_DATA_HOME = None
XDG_DATA_DIRS = None
XDG_CONFIG_HOME = None
XDG_CONFIG_DIRS = None
XDG_CACHE_HOME = None

def _set_basedirs():
	'''This method sets the global configuration paths for according to the
	freedesktop basedir specification.
	'''
	global ZIM_DATA_DIR
	global XDG_DATA_HOME
	global XDG_DATA_DIRS
	global XDG_CONFIG_HOME
	global XDG_CONFIG_DIRS
	global XDG_CACHE_HOME

	# Detect if we are running from the source dir
	if os.path.isfile('./zim.py'):
		scriptdir = '.' # maybe running module in test / debug
	else:
		scriptdir = os.path.dirname(sys.argv[0])
	zim_data_dir = Dir(scriptdir + '/data')
	if zim_data_dir.exists():
		ZIM_DATA_DIR = zim_data_dir
	else:
		ZIM_DATA_DIR = None

	if 'XDG_DATA_HOME' in os.environ:
		XDG_DATA_HOME = Dir(os.environ['XDG_DATA_HOME'])
	else:
		XDG_DATA_HOME = Dir('~/.local/share/')

	if 'XDG_DATA_DIRS' in os.environ:
		XDG_DATA_DIRS = map(Dir, os.environ['XDG_DATA_DIRS'].split(':'))
	else:
		XDG_DATA_DIRS = map(Dir, ('/usr/share/', '/usr/local/share/'))

	if 'XDG_CONFIG_HOME' in os.environ:
		XDG_CONFIG_HOME = Dir(os.environ['XDG_CONFIG_HOME'])
	else:
		XDG_CONFIG_HOME = Dir('~/.config/')

	if 'XDG_CONFIG_DIRS' in os.environ:
		XDG_CONFIG_DIRS = map(Dir, os.environ['XDG_CONFIG_DIRS'].split(':'))
	else:
		XDG_CONFIG_DIRS = [Dir('/etc/xdg/')]

	if 'XDG_CACHE_HOME' in os.environ:
		XDG_CACHE_HOME = Dir(os.environ['XDG_CACHE_HOME'])
	else:
		XDG_CACHE_HOME = Dir('~/.cache')

# Call on module initialization to set defaults
_set_basedirs()

def data_dirs(path=None):
	'''Generator for paths that contain zim data files. These will be the
	equivalent of e.g. /usr/share/zim, /usr/local/share/zim etc..
	'''
	zimpath = ['zim']
	if path:
		if isinstance(path, basestring):
			path = [path]
		assert not path[0] == 'zim'
		zimpath.extend(path)

	yield XDG_DATA_HOME.subdir(zimpath)

	if ZIM_DATA_DIR:
		if path:
			yield ZIM_DATA_DIR.subdir(path)
		else:
			yield ZIM_DATA_DIR

	for dir in XDG_DATA_DIRS:
		yield dir.subdir(zimpath)

def data_dir(path):
	'''Takes a path relative to the zim data dir and returns the first subdir
	found doing a lookup over all data dirs.
	'''
	for dir in data_dirs(path):
		if dir.exists():
			return dir

def data_file(path):
	'''Takes a path relative to the zim data dir and returns the first file
	found doing a lookup over all data dirs.
	'''
	for dir in data_dirs():
		file = dir.file(path)
		if file.exists():
			return file

def config_dirs():
	'''Generator that first yields the equivalent of ~/.config/zim and
	/etc/xdg/zim and then continous with the data dirs. Zim is not strictly
	XDG conformant by installing default config files in /usr/share/zim instead
	of in /etc/xdg/zim. Therefore this function yields both.
	'''
	yield XDG_CONFIG_HOME.subdir(('zim'))
	for dir in XDG_CONFIG_DIRS:
		yield dir.subdir(('zim'))
	for dir in data_dirs():
		yield dir

def config_file(path):
	'''Takes a path relative to the zim config dir and returns a file equivalent
	to ~/.config/zim/path . Based on the file extension a ConfigDictFile object,
	a ConfigListFile object or a normal File object is returned. In the case a
	ConfigDictFile is returned the default is also set when needed.
	'''
	if isinstance(path, basestring):
		path = [path]
	zimpath = ['zim'] + list(path)
	file = XDG_CONFIG_HOME.file(zimpath)
	if path[-1].endswith('.conf') or path[-1].endswith('.list'):
		if path[-1].endswith('.conf'): klass = ConfigDictFile
		else: klass = ConfigListFile

		if not file.exists():
			for dir in config_dirs():
				default = dir.file(path)
				if default.exists():
					break
			else:
				default is None
		else:
			default = None

		return klass(file, default=default)
	else:
		return file


class ConfigPathError(Exception):
	pass


class ListDict(dict):
	'''Class that behaves like a dict but keeps items in same order.
	Used as base class for e.g. for config objects were writing should be
	in a predictable order.
	'''

	def __init__(self):
		self.order = []

	def __setitem__(self, k, v):
		dict.__setitem__(self, k, v)
		if not k in self.order:
			self.order.append(k)

	def items(self):
		for k in self.order:
			yield (k, self[k])

	def set_order(self, order):
		'''Change the order in which items are listed by setting a list
		of keys. Keys not in the list are moved to the end. Keys that are in
		the list but not in the dict will be ignored.
		'''
		oldorder = set(self.order)
		neworder = set(order)
		for k in neworder - oldorder: # keys not in the dict
			order.remove(k)
		for k in oldorder - neworder: # keys not in the list
			order.append(k)
		sneworder = set(order)
		assert neworder == oldorder
		self.order = order

	def check_is_int(self, key, default):
		'''Asserts that the value for 'key' is an int. If this is not
		the case or when no value is set at all for 'key'.
		'''
		if not key in self:
			self[key] = default
		elif not isinstance(self[key], int):
			logger.warn('Invalid config value for %s: "%s" - should be an integer')
			self[key] = default

	def check_is_float(self, key, default):
		'''Asserts that the value for 'key' is a float. If this is not
		the case or when no value is set at all for 'key'.
		'''
		if not key in self:
			self[key] = default
		elif not isinstance(self[key], float):
			logger.warn('Invalid config value for %s: "%s" - should be a decimal number')
			self[key] = default

	def check_is_coord(self, key, default):
		'''Asserts that the value for 'key' is a coordinate
		(a tuple of 2 ints) and sets it to default if this is not the
		case or when no value is set at all for 'key'.
		'''
		if not key in self:
			self[key] = default
		else:
			v = self[key]
			if not (isinstance(v, tuple)
				and len(v) == 2
				and isinstance(v[0], int)
				and isinstance(v[1], int)  ):
				logger.warn('Invalid config value for %s: "%s" - should be a coordinate')
				self[key] = default


class ConfigList(ListDict):
	'''This class supports config files that exist of two columns separated
	by whitespace. It inherits from ListDict to ensure the list remain in
	the same order when it is written to file again. When a file path is set
	for this object it will be used to try reading from any from the config
	and data directories while using the config home directory for writing.
	'''

	_fields_re = re.compile(r'(?:\\.|\S)+') # match escaped char or non-whitespace
	_escaped_re = re.compile(r'\\(.)') # match single escaped char
	_escape_re = re.compile(r'([\s\\])') # match chars to escape

	def parse(self, text):
		if isinstance(text, basestring):
			text = text.splitlines(True)

		for line in text:
			line = line.strip()
			if line.isspace() or line.startswith('#'):
				continue
			cols = self._fields_re.findall(line)
			if len(cols) == 1:
				cols[1] = None # empty string in second column
			else:
				assert len(cols) >= 2
				if len(cols) > 2 and not cols[2].startswith('#'):
					logger.warn('trailing data') # FIXME better warning
			for i in range(0, 2):
				cols[i] = self._escaped_re.sub(r'\1', cols[i])
			self[cols[0]] = cols[1]

	def dump(self):
		text = TextBuffer()
		for k, v in self.items():
			k = self._escape_re.sub(r'\\\1', k)
			v = self._escape_re.sub(r'\\\1', v)
			text.append("%s\t%s\n" % (k, v))
		return text.get_lines()


class ConfigDict(ListDict):
	'''Config object which wraps a dict of dicts.
	These are represented as INI files where each sub-dict is a section.
	Sections are auto-vivicated when getting a non-existing key.
	Each section is in turn a ListDict.
	'''

	def __getitem__(self, k):
		if not k in self:
			self[k] = ListDict()
		return dict.__getitem__(self, k)

	def parse(self, text):
		if isinstance(text, basestring):
			text = text.splitlines(True)
		setion = None
		for line in text:
			line = line.strip()
			if not line or line.startswith('#'):
				continue
			elif line.startswith('[') and line.endswith(']'):
				name = line[1:-1].strip()
				section = self[name]
			else:
				parameter, value = line.split('=', 2)
				parameter = parameter.rstrip()
				value = self._convert_value(value.lstrip())
				section[parameter] = value

	_int_re = re.compile('^[0-9]+$')
	_float_re = re.compile('^[0-9]+\\.[0-9]+$')
	_coord_re = re.compile('^\\(\\s*[0-9]+\\s*,\\s*[0-9]+\\s*\\)$')

	def _convert_value(self, value):
		if value == 'True': return True
		elif value == 'False': return False
		elif self._int_re.match(value): return int(value)
		elif self._float_re.match(value): return float(value)
		elif self._coord_re.match(value):
			x,y = map(int, value[1:-1].split(','))
			return (x, y)
		else: return value

	def dump(self):
		lines = []
		for section, parameters in self.items():
			lines.append('[%s]\n' % section)
			for param, value in parameters.items():
				# TODO: how to encode line endings in value ?
				lines.append('%s=%s\n' % (param, value))
			lines.append('\n')
		return lines


class ConfigFile(ListDict):
	'''Base class for ConfigDictFile and ConfigListFile, can not be
	instantiated on its own.
	'''

	def __init__(self, file, default=None):
		ListDict.__init__(self)
		self.file = file
		self.default = default
		try:
			self.read()
		except ConfigPathError:
			pass

	def read(self):
		# TODO: flush dict first ?
		if self.file.exists():
			self.parse(self.file.readlines())
		elif self.default:
			self.parse(self.default.readlines())
		else:
			raise ConfigPathError, 'Config file \'%s\' does not exist and no default set' % self.file

	def write(self):
		self.file.writelines(self.dump())


class ConfigDictFile(ConfigFile, ConfigDict):
	pass


class ConfigListFile(ConfigFile, ConfigList):
	pass


class HeadersDict(ListDict):
	'''This class maps a set of headers in the rfc822 format.

	Header names are always kept in "title()" format to ensure
	case-insensitivity.
	'''

	_is_header_re = re.compile('^([\w\-]+):\s+(.*)')
	_is_continue_re = re.compile('^(\s+)(?=\S)')

	def __init__(self, text=None):
		ListDict.__init__(self)
		if not text is None:
			self.parse(text)

	def __getitem__(self, k):
		return ListDict.__getitem__(self, k.title())

	def __setitem__(self, k, v):
		return ListDict.__setitem__(self, k.title(), v)

	def read(self, lines):
		'''Checks for headers at the start of the list of lines and if any
		reads them into the dict untill the first empty line. Will shift any
		lines belonging to the header block, so after this method returns the
		input does no longer contain the header block.
		'''
		self._parse(lines, fatal=False)
		if lines and lines[0].isspace():
			lines.pop(0)

	def parse(self, text):
		'''Adds headers defined in 'text' to the dict. Text can either be
		a string or a list of lines.

		Raises a ParsingError when 'text' is not a valid header block.
		Trailing whitespace is ignored.
		'''
		if isinstance(text, basestring):
			lines = text.rstrip().splitlines(True)
		else:
			lines = text[:] # make copy so we do not destry the original
		self._parse(lines)

	def _parse(self, lines, fatal=True):
		header = None
		while lines:
			is_header = self._is_header_re.match(lines[0])
			if is_header:
				header = is_header.group(1)
				value  = is_header.group(2)
				self[header] = value.strip()
			elif self._is_continue_re.match(lines[0]) and not header is None:
				self[header] += '\n' + lines[0].strip()
			else:
				if fatal:
					raise ParsingError, 'Not a valid rfc822 header block'
				else:
					break
			lines.pop(0)

	def dump(self, strict=False):
		'''Returns the dict as a list of lines defining a rfc822 header block.

		If 'strict' is set to True lines will be properly terminated
		with '\r\n' instead of '\n'.
		'''
		buffer = []
		for k, v in self.items():
			v = v.strip().replace('\n', '\n\t')
			buffer.extend((k, ': ', v, '\n'))
		text = ''.join(buffer)

		if strict:
			text = text.replace('\n', '\r\n')

		return text.splitlines(True)
