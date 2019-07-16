#!/usr/bin/env python3
import configparser
import argparse
from dataclasses import dataclass

from cffi import FFI

ffi = FFI()
lalpm = ffi.dlopen("libalpm.so")

ffi.cdef('''
typedef struct __alpm_list_t {
	/** data held by the list node */
	void *data;
	/** pointer to the previous node */
	struct __alpm_list_t *prev;
	/** pointer to the next node */
	struct __alpm_list_t *next;
} alpm_list_t;

typedef struct __alpm_handle_t alpm_handle_t;
typedef struct __alpm_db_t alpm_db_t;
typedef struct __alpm_pkg_t alpm_pkg_t;
typedef struct __alpm_trans_t alpm_trans_t;
typedef enum _alpm_errno_t {
	ALPM_ERR_OK = 0,
	ALPM_ERR_MEMORY,
	ALPM_ERR_SYSTEM,
	ALPM_ERR_BADPERMS,
	ALPM_ERR_NOT_A_FILE,
	ALPM_ERR_NOT_A_DIR,
	ALPM_ERR_WRONG_ARGS,
	ALPM_ERR_DISK_SPACE,
	/* Interface */
	ALPM_ERR_HANDLE_NULL,
	ALPM_ERR_HANDLE_NOT_NULL,
	ALPM_ERR_HANDLE_LOCK,
	/* Databases */
	ALPM_ERR_DB_OPEN,
	ALPM_ERR_DB_CREATE,
	ALPM_ERR_DB_NULL,
	ALPM_ERR_DB_NOT_NULL,
	ALPM_ERR_DB_NOT_FOUND,
	ALPM_ERR_DB_INVALID,
	ALPM_ERR_DB_INVALID_SIG,
	ALPM_ERR_DB_VERSION,
	ALPM_ERR_DB_WRITE,
	ALPM_ERR_DB_REMOVE,
	/* Servers */
	ALPM_ERR_SERVER_BAD_URL,
	ALPM_ERR_SERVER_NONE,
	/* Transactions */
	ALPM_ERR_TRANS_NOT_NULL,
	ALPM_ERR_TRANS_NULL,
	ALPM_ERR_TRANS_DUP_TARGET,
	ALPM_ERR_TRANS_NOT_INITIALIZED,
	ALPM_ERR_TRANS_NOT_PREPARED,
	ALPM_ERR_TRANS_ABORT,
	ALPM_ERR_TRANS_TYPE,
	ALPM_ERR_TRANS_NOT_LOCKED,
	ALPM_ERR_TRANS_HOOK_FAILED,
	/* Packages */
	ALPM_ERR_PKG_NOT_FOUND,
	ALPM_ERR_PKG_IGNORED,
	ALPM_ERR_PKG_INVALID,
	ALPM_ERR_PKG_INVALID_CHECKSUM,
	ALPM_ERR_PKG_INVALID_SIG,
	ALPM_ERR_PKG_MISSING_SIG,
	ALPM_ERR_PKG_OPEN,
	ALPM_ERR_PKG_CANT_REMOVE,
	ALPM_ERR_PKG_INVALID_NAME,
	ALPM_ERR_PKG_INVALID_ARCH,
	ALPM_ERR_PKG_REPO_NOT_FOUND,
	/* Signatures */
	ALPM_ERR_SIG_MISSING,
	ALPM_ERR_SIG_INVALID,
	/* Deltas */
	ALPM_ERR_DLT_INVALID,
	ALPM_ERR_DLT_PATCHFAILED,
	/* Dependencies */
	ALPM_ERR_UNSATISFIED_DEPS,
	ALPM_ERR_CONFLICTING_DEPS,
	ALPM_ERR_FILE_CONFLICTS,
	/* Misc */
	ALPM_ERR_RETRIEVE,
	ALPM_ERR_INVALID_REGEX,
	/* External library errors */
	ALPM_ERR_LIBARCHIVE,
	ALPM_ERR_LIBCURL,
	ALPM_ERR_EXTERNAL_DOWNLOAD,
	ALPM_ERR_GPGME
} alpm_errno_t;

const char *alpm_version(void);

alpm_handle_t *alpm_initialize(const char *root, const char *dbpath, alpm_errno_t *err);
int alpm_release(alpm_handle_t *handle);

alpm_db_t *alpm_get_localdb(alpm_handle_t *handle);

alpm_list_t *alpm_db_search(alpm_db_t *db, const alpm_list_t *needles);

const char *alpm_pkg_get_name(alpm_pkg_t *pkg);

//off_t alpm_pkg_get_isize(alpm_pkg_t *pkg);
uint64_t alpm_pkg_get_isize(alpm_pkg_t *pkg);
''')


def bytes_humanize(size) -> str:
    for prefix in ["B", "KiB", "MiB", "GiB", "TiB"]:
        size /= 1024
        if size < 1:
            break
    size *= 1024
    return f"{size:.02f}{prefix}"


@dataclass
class Package:
    name: str
    size: int


def read_pacman_config():
    config = configparser.ConfigParser(allow_no_value=True)
    config.read_dict({
        'options': {
            'RootDir': '/',
            'DBPath': '/var/lib/pacman',
            'CacheDir': '/var/cache/pacman/pkg'
        }
    })
    config.read("/etc/pacman.conf")
    return config


class ALPM:
    def __init__(self, root_dir: str, db_path: str):
        self.handle = lalpm.alpm_initialize(root_dir.encode(),
                                            db_path.encode(),
                                            ffi.NULL)
        self.local_db = lalpm.alpm_get_localdb(self.handle)

    def search_db(self, name):
        needle = ffi.new("alpm_list_t *",
                         [ffi.new("char[]", name.encode()),
                          ffi.NULL,
                          ffi.NULL]
                         )
        res_array = []
        res = lalpm.alpm_db_search(self.local_db, needle)
        while res != ffi.NULL:
            pkg = ffi.cast("alpm_pkg_t *", res.data)
            name = ffi.string(lalpm.alpm_pkg_get_name(pkg))
            size = lalpm.alpm_pkg_get_isize(pkg)
            res_array.append(Package(name.decode(), size))
            res = ffi.cast("alpm_list_t *", res.next)
        return res_array

    @staticmethod
    def version():
        return ffi.string(lalpm.alpm_version()).decode()

    def __del__(self):
        lalpm.alpm_release(self.handle)


def main(human_readable, show_total):
    config = read_pacman_config()
    root_dir, db_path = \
        config.get('options', 'RootDir'), \
        config.get('options', 'DBPath'),

    alpm = ALPM(root_dir, db_path)

    packages = alpm.search_db(".*")
    packages.sort(key=lambda p: p.size)

    if show_total:
        s = sum(map(lambda p: p.size, packages))
        if human_readable:
            show = bytes_humanize(s)
        else:
            show = str(s)
        print(show)
    else:
        for p in packages:
            if human_readable:
                display_size = bytes_humanize(p.size)
            else:
                display_size = str(p.size)
            print(f"{p.name} {display_size}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Show size of currently installed pacman packages.",
                                     add_help=False)
    parser.add_argument('-h', action='store_true',
                        help='Print human-readable sizes')
    parser.add_argument('-s', action='store_true',
                        help='Print total size of installed packages')
    parser.add_argument('--help', action='help', help='Show this message')
    args = parser.parse_args()

    main(args.h, args.s)
