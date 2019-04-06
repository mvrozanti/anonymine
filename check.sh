#!/bin/sh

# check.sh $(srcdir) $(builddir)
srcdir=$1
builddir=$2

cat > ${builddir}check.py << __EOF__
# check.py enginecfg
import anonymine_engine
import sys

for mode in ('moore', 'hex', 'neumann'):
    engine = anonymine_engine.game_engine(
        sys.argv[1],
        width=10, height=10,
        mines=20,
        flagcount=True, guessless=True,
        gametype=mode
    )
    engine.init_field((3,4))
    assert 'X' not in str(engine.field)
__EOF__

cd $1

file1="${builddir}enginecfg.out"
file2="${builddir}enginecfg.user"
file3="${srcdir}enginecfg.fallback"
for enginecfg in $file1 $file2 $file3; do
    if [ -f $enginecfg ]; then
        break
    fi
done

has_any=0
fail_any=0
v_ck="import sys; assert sys.version_info[0] == 3 or sys.version_info[1] >= 6"
for interpreter in python2 python3 python; do
    if $interpreter -c "$v_ck" 2>/dev/null ; then
        has_any=1
        if ! $interpreter ${builddir}check.py $enginecfg; then
            fail_any=1
        fi
    fi
done

if [ $has_any -eq 0 ]; then
    echo "No python interpreters found." >/dev/stderr
    exit 42
fi

if [ $fail_any -eq 1 ]; then
    exit 23
fi
