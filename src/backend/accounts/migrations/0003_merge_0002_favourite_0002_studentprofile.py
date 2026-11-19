"""Reconcile the two 0002 migrations that reached develop independently.

`0002_favourite` came from the favourites branch and `0002_studentprofile`
from student discovery. Both were written against `0001_initial` and neither
knew about the other, so each is a leaf of the accounts graph and `migrate`
refuses to run until one path through them exists.

Nothing to do here: the two create unrelated tables, `Favourite` against a
student account and a spot, `StudentProfile` against a user. Declaring both as
dependencies is the whole fix, and the order Django then picks between them
does not matter.

The filenames do not collide, so git merged the branches without complaint and
the conflict only appeared when the deployed `migrate` ran. Worth knowing for
the next pair of branches that each add a migration to the same app.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_favourite"),
        ("accounts", "0002_studentprofile"),
    ]

    operations = []
