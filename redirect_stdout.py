from contextlib import contextmanager
import ctypes
import io
import os, sys
import tempfile

### Old ####################################################
# libc = ctypes.CDLL(None)
# c_stdout = ctypes.c_void_p.in_dll(libc, 'stdout')
############################################################

### ALL THIS IS NEW ########################################
if sys.version_info < (3, 5):
    libc = ctypes.CDLL(ctypes.util.find_library('c'))
else:
    if hasattr(sys, 'gettotalrefcount'): libc = ctypes.CDLL('ucrtbased') # debug build
    else: libc = ctypes.CDLL('api-ms-win-crt-stdio-l1-1-0')

kernel32 = ctypes.WinDLL('kernel32')
STD_OUTPUT_HANDLE = -11
c_stdout = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
############################################################

@contextmanager
def stdout_redirector(stream):
    # The original fd stdout points to. Usually 1 on POSIX systems.
    original_stdout_fd = sys.stdout.fileno()

    def _redirect_stdout(to_fd):
        """Redirect stdout to the given file descriptor."""
        # Flush the C-level buffer stdout
        libc.fflush(None)   #### CHANGED THIS ARG TO NONE #############
        # Flush and close sys.stdout - also closes the file descriptor (fd)
        sys.stdout.close()
        # Make original_stdout_fd point to the same file as to_fd
        os.dup2(to_fd, original_stdout_fd)
        # Create a new sys.stdout that points to the redirected fd
        sys.stdout = io.TextIOWrapper(os.fdopen(original_stdout_fd, 'wb'))

    # Save a copy of the original stdout fd in saved_stdout_fd
    saved_stdout_fd = os.dup(original_stdout_fd)
    try:
        # Create a temporary file and redirect stdout to it
        tfile = tempfile.TemporaryFile(mode='w+b')
        _redirect_stdout(tfile.fileno())
        # Yield to caller, then redirect stdout back to the saved fd
        yield
        _redirect_stdout(saved_stdout_fd)
        # Copy contents of temporary file to the given stream
        tfile.flush()
        tfile.seek(0, io.SEEK_SET)
        stream.write(tfile.read())
    finally:
        tfile.close()
        os.close(saved_stdout_fd)

if __name__ == '__main__':
    #### Test it
    f = io.BytesIO()

    with stdout_redirector(f):
        print('foobar')
        print(12)
        libc.puts(b'this comes from C')
        os.system('echo and this is from echo')
        
    print('Got stdout: "{0}"'.format(f.getvalue().decode()))