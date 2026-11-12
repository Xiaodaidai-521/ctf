"""Validate private key paths using native ownership and permissions."""
import os
import stat


def is_private_path(path, *, directory=False):
    info = path.lstat()
    if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
        return False
    if os.name != 'nt':
        return info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == (0o700 if directory else 0o600)
    # Windows chmod does not protect secrets. Require a protected, current-user
    # DACL and reject junctions/symlinks, NULL DACLs and foreign allow entries.
    if info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        return False
    try:
        import win32api
        import win32con
        import win32security as security
        token = security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
        try:
            sid = security.GetTokenInformation(token, security.TokenUser)[0]
        finally:
            token.Close()
        descriptor = security.GetNamedSecurityInfo(str(path), security.SE_FILE_OBJECT,
            security.OWNER_SECURITY_INFORMATION | security.DACL_SECURITY_INFORMATION)
        dacl = descriptor.GetSecurityDescriptorDacl()
        control, _ = descriptor.GetSecurityDescriptorControl()
        if descriptor.GetSecurityDescriptorOwner() != sid or dacl is None or not control & security.SE_DACL_PROTECTED:
            return False
        allowed = False
        for index in range(dacl.GetAceCount()):
            ace = dacl.GetAce(index)
            kind, flags = ace[0]
            if kind != security.ACCESS_ALLOWED_ACE_TYPE or flags & security.INHERITED_ACE or ace[2] != sid:
                return False
            allowed = allowed or bool(ace[1] & 1)  # FILE_READ_DATA / FILE_LIST_DIRECTORY
        return allowed
    except Exception:
        # pywintypes.error is not an OSError. An unreadable or malformed native
        # descriptor must deny access, just like an unavailable ACL dependency.
        return False
