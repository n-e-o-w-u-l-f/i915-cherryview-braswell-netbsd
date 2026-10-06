#!/usr/bin/env python3
"""Port native completion counting and timeout contracts from the frozen Linux API.

Keep the real NetBSD mutex/CV backend. Counter saturation, deadline races,
remaining ticks and return widths match the Linux API. Fatal-signal-only waits,
IO accounting, FIFO wake ordering and caller destruction remain separate gates.
"""
import argparse
import difflib
from pathlib import Path
import re
import subprocess
PIN='03d918f6d0e81fa05b8f1160eca0628ad39988a6'
PATH='sys/external/bsd/common/include/linux/completion.h'

def adapt(old):
 s=old.replace('int\t\tc_done;','unsigned int\tc_done;')
 assert s!=old
 a=s.index('\t/*\n\t * c_done is either');b=s.index('\n\tunsigned int\tc_done;',a)
 s=s[:a]+'''\t/* Zero blocks; UINT_MAX permanently completes until reinitialization.
\t * Other values count successful claims, matching Linux saturation.
\t */'''+s[b:]
 def replace(name,text):
  nonlocal s
  pattern=r'static inline [^\n]+\n'+name+r'\([^\n]*(?:\n[^\n]*)?\)\n\{[\s\S]*?\n\}'
  # The optional argument continuation is required only for timeout APIs.
  match=re.search(pattern,s)
  if not match:raise RuntimeError('missing native function '+name)
  s=s[:match.start()]+text+s[match.end():]
 replace('complete','''static inline void
complete(struct completion *completion)
{
    mutex_enter(&completion->c_lock);
    if (completion->c_done != UINT_MAX)
        completion->c_done++;
    cv_signal(&completion->c_cv);
    mutex_exit(&completion->c_lock);
}''')
 replace('complete_all','''static inline void
complete_all(struct completion *completion)
{
    mutex_enter(&completion->c_lock);
    completion->c_done = UINT_MAX;
    cv_broadcast(&completion->c_cv);
    mutex_exit(&completion->c_lock);
}''')
 replace('_completion_claim','''static inline void
_completion_claim(struct completion *completion)
{
    KASSERT(mutex_owned(&completion->c_lock));
    KASSERT(completion->c_done != 0);
    if (completion->c_done != UINT_MAX)
        completion->c_done--;
}''')
 helper='''/* Native CV slices retain the complete Linux timeout budget. */
static inline unsigned long
_linux_wait_completion_timeout(struct completion *completion,
    unsigned long ticks, bool interruptible, int *error)
{
    unsigned long result = 0;
    *error = 0;
    mutex_enter(&completion->c_lock);
    while (completion->c_done == 0 && ticks != 0) {
        unsigned long slice = MIN(ticks, (unsigned long)INT_MAX/2);
        unsigned int start = getticks();
        int cv_error = interruptible ?
            cv_timedwait_sig(&completion->c_cv, &completion->c_lock, slice) :
            cv_timedwait(&completion->c_cv, &completion->c_lock, slice);
        unsigned int elapsed = (unsigned int)getticks() - start;
        if (cv_error == EWOULDBLOCK && elapsed < slice)
            elapsed = slice;
        ticks -= MIN(ticks, (unsigned long)elapsed);
        /* Linux claims a completion that wins the timeout/signal race. */
        if (completion->c_done != 0)
            break;
        if (interruptible && (cv_error == EINTR || cv_error == ERESTART)) {
            *error = -ERESTARTSYS;
            goto out;
        }
        KASSERT(cv_error == 0 || cv_error == EWOULDBLOCK);
    }
    if (completion->c_done != 0) {
        _completion_claim(completion);
        result = ticks != 0 ? ticks : 1;
    }
out:
    mutex_exit(&completion->c_lock);
    return result;
}

'''
 replace('wait_for_completion_interruptible_timeout',helper+'''static inline long
wait_for_completion_interruptible_timeout(struct completion *completion,
    unsigned long ticks)
{
    int error;
    unsigned long remaining = _linux_wait_completion_timeout(completion,
        ticks, true, &error);
    return error != 0 ? error : (long)remaining;
}''')
 replace('wait_for_completion_timeout','''static inline unsigned long
wait_for_completion_timeout(struct completion *completion, unsigned long ticks)
{
    int error;
    unsigned long remaining = _linux_wait_completion_timeout(completion,
        ticks, false, &error);
    KASSERT(error == 0);
    return remaining;
}''')
 anchor='\n#endif\t/* _LINUX_COMPLETION_H_ */'
 assert s.count(anchor)==1
 s=s.replace(anchor,'''/* Lock acquisition also drains an in-flight complete() before returning. */
static inline bool
completion_done(struct completion *completion)
{
    bool done;
    mutex_enter(&completion->c_lock);
    done = completion->c_done != 0;
    mutex_exit(&completion->c_lock);
    return done;
}
'''+anchor)
 return s

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--netbsd-tree',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 assert subprocess.check_output(['git','-C',str(a.netbsd_tree),'rev-parse','HEAD'],text=True).strip()==PIN
 if a.out.exists():p.error('preserve existing output')
 old=subprocess.check_output(['git','-C',str(a.netbsd_tree),'show',PIN+':'+PATH],text=True)
 new=adapt(old);a.out.parent.mkdir(parents=True,exist_ok=True)
 a.out.write_text(''.join(difflib.unified_diff(old.splitlines(keepends=True),new.splitlines(keepends=True),fromfile='a/'+PATH,tofile='b/'+PATH)))

if __name__=='__main__':main()
