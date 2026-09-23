# -*- coding: utf-8 -*-
"""Every class a mockup uses that the product's stylesheet also styles.

Building a mockup from the real stylesheets is what makes it evidence. It is also
what makes every class name you invent a coin flip against rules you did not
write, and a collision is silent: the page renders, it just renders wrong. Ten
were found this way across one project's mockups and none was visible by eye -
`.flag` was an uppercase pill that turned a step name into a shout, `.rail` had
`height:100vh`, `.mk` was `position:absolute;left:-19px`, `.jspine` carried
`padding:4px 0 40vh 12px`.

Run it on every page a generator writes, not once at the end by hand. The one
that was skipped is the one that cost an afternoon.

    python class_check.py --css app.css --html page.html \\
        --borrow view --borrow mono

Exit status is 1 when anything collides, so a generator can fail on it.
"""
import argparse
import io
import re
import sys


def classes_used(html: str) -> set:
    """Every token inside a class="..." attribute."""
    return {c for m in re.finditer(r'class="([^"]+)"', html) for c in m.group(1).split()}


def classes_styled(css: str) -> set:
    """Every class name any selector in the stylesheet mentions.

    Deliberately blunt: a name that appears anywhere in any selector can reach
    your element through a descendant or compound rule, so the check does not try
    to work out whether this particular rule would match.
    """
    return set(re.findall(r'\.([A-Za-z][\w-]*)', css))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--css', action='append', required=True,
                   help='a product stylesheet; repeat for each one the page loads')
    p.add_argument('--html', required=True, help='the mockup page, or its body fragment')
    p.add_argument('--borrow', action='append', default=[],
                   help='a class reused from the product on purpose; repeat')
    a = p.parse_args()

    css = '\n'.join(io.open(f, encoding='utf-8').read() for f in a.css)
    html = io.open(a.html, encoding='utf-8').read()

    hits = sorted((classes_used(html) & classes_styled(css)) - set(a.borrow))
    if not hits:
        print('no collisions (%d classes used, %d borrowed on purpose)'
              % (len(classes_used(html)), len(a.borrow)))
        return 0

    print('COLLIDES with the product stylesheet:')
    for name in hits:
        rule = re.search(r'([^{}]*\.' + re.escape(name) + r'\b[^{}]*)\{([^}]*)\}', css)
        print('  .%-18s %s' % (name, (rule.group(0)[:110] + '...') if rule else '(see the sheet)'))
    print('\nRename them, or pass --borrow for each one you are reusing on purpose.')
    return 1


if __name__ == '__main__':
    sys.exit(main())
