"""Meson build for radare2"""

import argparse
import glob
import logging
import os
import re
import shutil
import subprocess
import sys

BUILDDIR = 'build'
BACKENDS = ['ninja', 'vs2015', 'vs2017']

PATH_FMT = {}

MESON = None
ROOT = None
log = None

def set_global_variables():
    """[R_API] Set global variables"""
    global log
    global ROOT
    global MESON

    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir))

    logging.basicConfig(format='[%(name)s][%(levelname)s]: %(message)s',
                        level=logging.DEBUG)
    log = logging.getLogger('r2-meson')

    with open(os.path.join(ROOT, 'configure.acr')) as f:
        f.readline()
        version = f.readline().split()[1].rstrip()

    if os.name == 'nt':
        meson = os.path.join(os.path.dirname(sys.executable), 'Scripts', 'meson.py')
        MESON = [sys.executable, meson]
    else:
        MESON = ['meson']

    PATH_FMT['ROOT'] = ROOT
    PATH_FMT['R2_VERSION'] = version

    log.debug('Root: %s', ROOT)
    log.debug('Meson: %s', MESON)
    log.debug('Version: %s', version)

def meson(root, build, prefix=None, backend=None,
          release=False, shared=False, *, options=[]):
    """[R_API] Invoke meson"""
    command = MESON + [root, build]
    if prefix:
        command.append('--prefix={}'.format(prefix))
    if backend:
        command.append('--backend={}'.format(backend))
    if release:
        command.append('--buildtype=release')
    if shared:
        command.append('--default-library=shared')
    else:
        command.append('--default-library=static')
    if options:
        command.extend(options)

    log.debug('Invoking meson: %s', command)
    ret = subprocess.call(command)
    if ret != 0:
        log.error('Meson error. Exiting.')
        sys.exit(1)

def ninja(folder, *targets):
    """[R_API] Invoke ninja"""
    command = ['ninja', '-C', folder]
    if targets:
        command.extend(targets)
    log.debug('Invoking ninja: %s', command)
    ret = subprocess.call(command)
    if ret != 0:
        log.error('Ninja error. Exiting.')
        sys.exit(1)

def msbuild(project, *params):
    """[R_API] Invoke MSbuild"""
    command = ['msbuild', project]
    if params:
        command.extend(params)
    log.info('Invoking MSbuild: %s', command)
    ret = subprocess.call(command)
    if ret != 0:
        log.error('MSbuild error. Exiting.')
        sys.exit(1)

def copytree(src, dst, exclude=()):
    src = src.format(**PATH_FMT)
    dst = dst.format(**PATH_FMT)
    log.debug('copytree "%s" -> "%s"', src, dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*exclude) if exclude else None)

def move(src, dst):
    src = src.format(**PATH_FMT)
    dst = dst.format(**PATH_FMT)
    term = os.path.sep if os.path.isdir(dst) else ''
    log.debug('move "%s" -> "%s%s"', src, dst, term)
    for file in glob.iglob(src):
        shutil.move(file, dst)

def copy(src, dst):
    src = src.format(**PATH_FMT)
    dst = dst.format(**PATH_FMT)
    term = os.path.sep if os.path.isdir(dst) else ''
    log.debug('copy "%s" -> "%s%s"', src, dst, term)
    for file in glob.iglob(src, recursive='**' in src):
        shutil.copy2(file, dst)

def makedirs(path):
    path = path.format(**PATH_FMT)
    log.debug('makedirs "%s"', path)
    os.makedirs(path)

def xp_compat(builddir):
    log.info('Running XP compat script')

    with open(os.path.join(builddir, 'REGEN.vcxproj'), 'r') as f:
        version = re.search('<PlatformToolset>(.*)</PlatformToolset>', f.read()).group(1)

    if version.endswith('_xp'):
        log.info('Skipping %s', builddir)
        return

    log.debug('Translating from %s to %s_xp', version, version)
    newversion = version+'_xp'

    for f in glob.iglob(os.path.join(builddir, '**', '*.vcxproj'), recursive=True):
        with open(f, 'r') as proj:
            c = proj.read()
        c = c.replace(version, newversion)
        with open(f, 'w') as proj:
            proj.write(c)
            log.debug("%s .. OK", f)

def vs_dedup(builddir):
    """Remove duplicated dependency entries from vs project"""
    start = '<AdditionalDependencies>'
    end = ';%(AdditionalDependencies)'
    for f in glob.iglob(os.path.join(builddir, '**', '*.vcxproj'), recursive=True):
        with open(f) as proj:
            data = proj.read()
        idx = data.find(start)
        if idx < 0:
            continue
        idx += len(start)
        idx2 = data.find(end, idx)
        if idx2 < 0:
            continue
        libs = set(data[idx:idx2].split(';'))
        with open(f, 'w') as proj:
            proj.write(data[:idx])
            proj.write(';'.join(sorted(libs)))
            proj.write(data[idx2:])
        log.debug('%s processed', f)

def win_dist(args):
    """Create r2 distribution for Windows"""
    builddir = os.path.join(ROOT, args.dir)
    PATH_FMT['DIST'] = args.install
    PATH_FMT['BUILDDIR'] = builddir

    makedirs(r'{DIST}')
    copy(r'{BUILDDIR}\binr\**\*.exe', r'{DIST}')
    copy(r'{BUILDDIR}\libr\**\*.dll', r'{DIST}')
    if args.copylib:
        copy(r'{BUILDDIR}\libr\**\*.lib', r'{DIST}')
        copy(r'{BUILDDIR}\libr\**\*.a', r'{DIST}')
    win_dist_libr2()

def win_dist_libr2(**path_fmt):
    """[R_API] Add libr2 data/www/include/doc to dist directory"""
    PATH_FMT.update(path_fmt)

    copytree(r'{ROOT}\shlr\www', r'{DIST}\www')
    copytree(r'{ROOT}\libr\magic\d\default', r'{DIST}\share\radare2\{R2_VERSION}\magic')
    makedirs(r'{DIST}\share\radare2\{R2_VERSION}\syscall')
    copy(r'{BUILDDIR}\libr\syscall\d\*.sdb', r'{DIST}\share\radare2\{R2_VERSION}\syscall')
    makedirs(r'{DIST}\share\radare2\{R2_VERSION}\fcnsign')
    copy(r'{BUILDDIR}\libr\anal\d\*.sdb', r'{DIST}\share\radare2\{R2_VERSION}\fcnsign')
    makedirs(r'{DIST}\share\radare2\{R2_VERSION}\opcodes')
    copy(r'{BUILDDIR}\libr\asm\d\*.sdb', r'{DIST}\share\radare2\{R2_VERSION}\opcodes')
    makedirs(r'{DIST}\include\libr\sdb')
    makedirs(r'{DIST}\include\libr\r_util')
    copy(r'{ROOT}\libr\include\*.h', r'{DIST}\include\libr')
    copy(r'{ROOT}\libr\include\sdb\*.h', r'{DIST}\include\libr\sdb')
    copy(r'{ROOT}\libr\include\r_util\*.h', r'{DIST}\include\libr\r_util')
    makedirs(r'{DIST}\share\doc\radare2')
    copy(r'{ROOT}\doc\fortunes.*', r'{DIST}\share\doc\radare2')
    makedirs(r'{DIST}\share\radare2\{R2_VERSION}\format\dll')
    copy(r'{ROOT}\libr\bin\d\elf32', r'{DIST}\share\radare2\{R2_VERSION}\format')
    copy(r'{ROOT}\libr\bin\d\elf64', r'{DIST}\share\radare2\{R2_VERSION}\format')
    copy(r'{ROOT}\libr\bin\d\elf_enums', r'{DIST}\share\radare2\{R2_VERSION}\format')
    copy(r'{ROOT}\libr\bin\d\pe32', r'{DIST}\share\radare2\{R2_VERSION}\format')
    copy(r'{ROOT}\libr\bin\d\trx', r'{DIST}\share\radare2\{R2_VERSION}\format')
    copy(r'{BUILDDIR}\libr\bin\d\*.sdb', r'{DIST}\share\radare2\{R2_VERSION}\format\dll')
    copytree(r'{ROOT}\libr\cons\d', r'{DIST}\share\radare2\{R2_VERSION}\cons',
             exclude=('Makefile', 'meson.build'))
    makedirs(r'{DIST}\share\radare2\{R2_VERSION}\hud')
    copy(r'{ROOT}\doc\hud', r'{DIST}\share\radare2\{R2_VERSION}\hud\main')

def build(args):
    """ Build radare2 """
    log.info('Building radare2')
    r2_builddir = os.path.join(ROOT, args.dir)
    if not os.path.exists(r2_builddir):
        meson(ROOT, r2_builddir, prefix=args.prefix, backend=args.backend,
              release=args.release, shared=args.shared)
    if args.backend != 'ninja':
        vs_dedup(r2_builddir)
        if args.xp:
            xp_compat(r2_builddir)
        if not args.project:
            project = os.path.join(r2_builddir, 'radare2.sln')
            msbuild(project, '/m')
    else:
        ninja(r2_builddir)

def install(args):
    """ Install radare2 """
    if os.name == 'nt':
        win_dist(args)
        return
    log.warning('Install not implemented yet for this platform.')
    # TODO
    #if os.name == 'posix':
    #    os.system('DESTDIR="{destdir}" ninja -C {build} install'
    #            .format(destdir=destdir, build=args.dir))

def main():
    # Create logger and get applications paths
    set_global_variables()

    # Create parser
    parser = argparse.ArgumentParser(description='Mesonbuild scripts for radare2')
    parser.add_argument('--project', action='store_true',
            help='Create a visual studio project and do not build.')
    parser.add_argument('--release', action='store_true',
            help='Set the build as Release (remove debug info)')
    parser.add_argument('--backend', choices=BACKENDS, default='ninja',
            help='Choose build backend (default: %(default)s)')
    parser.add_argument('--shared', action='store_true',
            help='Link dynamically (shared library) rather than statically')
    parser.add_argument('--prefix', default=None,
            help='Set project installation prefix')
    parser.add_argument('--dir', default=BUILDDIR, required=False,
            help='Destination build directory (default: %(default)s)')
    parser.add_argument('--xp', action='store_true',
            help='Adds support for Windows XP')
    if os.name == 'nt':
        parser.add_argument('--install', help='Installation directory')
        parser.add_argument('--copylib', action='store_true',
            help='Copy static libraries to the installation directory')
    else:
        parser.add_argument('--install', action='store_true',
            help='Install radare2 after building')
    args = parser.parse_args()

    # Check arguments
    if args.project and args.backend == 'ninja':
        log.error('--project is not compatible with --backend ninja')
        sys.exit(1)
    if args.xp and args.backend == 'ninja':
        log.error('--xp is not compatible with --backend ninja')
        sys.exit(1)
    if os.name == 'nt' and args.install and os.path.exists(args.install):
        log.error('%s already exists', args.install)
        sys.exit(1)
    if os.name == 'nt' and not args.prefix:
        args.prefix = os.path.join(ROOT, args.dir, 'priv_install_dir')

    # Build it!
    log.debug('Arguments: %s', args)
    build(args)
    if args.install:
        install(args)

if __name__ == '__main__':
    main()
