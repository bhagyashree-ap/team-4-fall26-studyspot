"""Record the three attributes OpenStreetMap supplies and the city does not.

``indoor_seating``, ``venue_wifi`` and ``opening_hours`` arrive from the Overpass
API by way of ``data/osm.py``, which the importer merges over the DOHMH cafes.

All three are **nullable**, and that is the substance of this migration rather
than a detail of it. They are the only columns in this table where null means
*nobody has recorded this* rather than *this record has no such thing*, and the
default must therefore not be false. ``free_public_wifi`` is the cautionary
example: it is a non-null boolean whose false has to be explained in its own
help text, in the API documentation and in two places in the interface, because
false there means "no hotspot the city publishes within 25 m" and reads as "no
Wi-Fi". These columns do not have that problem, and acquiring it by taking a
default would throw away the reason the source was added.

``venue_wifi`` is deliberately a second column rather than an update to
``free_public_wifi``. The two are different claims about different things -- the
venue's own Wi-Fi, and a hotspot the city publishes near the point -- and a
single column would have to mean one of them.

Plain AddFields, like 0011 and unlike 0006 and 0007: none of the three is part
of ``search_vector``, so Django's refusal to alter a GeneratedField does not
apply and the vector is untouched. Nobody types an opening-hours expression
into a search box, and a boolean has no words to index.

One index, on ``indoor_seating`` alone, following the rule the earlier
migrations set: a column gets an index when it has a query parameter behind it.
``indoor_seating`` has a filter -- ``?indoor_seating=true`` narrows to the spots
somebody has recorded somewhere to sit inside -- and ``venue_wifi`` and
``opening_hours`` have none, so indexing them would be a write cost for nothing.
0011 added no index for exactly this reason.

That the filter exists for one of the three and not the others is not an
oversight. A filter over a three-state column has to decide what ``false``
means about the unrecorded majority, and only ``indoor_seating`` has an answer
worth offering: "recorded as having nowhere to sit inside" is a real, if small,
thing to ask for. ``?venue_wifi=false`` would be asking a question whose honest
answer is 42 rows out of 3,772, and whose tempting wrong answer is 3,478.
"""

from django.db import migrations, models

#: Plain rather than partial. The column is null on 3,647 of 3,772 rows, so a
#: `condition=Q(indoor_seating__isnull=False)` index would be a fraction of the
#: size -- but Django requires the condition spelled identically on the model
#: and here, and the table is small enough that the difference is theoretical.
INDOOR_SEATING_INDEX = models.Index(fields=["indoor_seating"], name="spots_indoor_idx")


class Migration(migrations.Migration):
    dependencies = [
        ("spots", "0011_outdoor_seating"),
    ]

    operations = [
        migrations.AddField(
            model_name="studyspot",
            name="indoor_seating",
            field=models.BooleanField(
                blank=True,
                null=True,
                help_text=(
                    "Whether OpenStreetMap records somewhere to sit inside. Null means "
                    "unrecorded, which is most spots: contributors have tagged it on 169 "
                    "cafes in the city. False is a contributor saying there is nowhere to sit "
                    "inside, which is a real answer and not the same as null."
                ),
            ),
        ),
        migrations.AddField(
            model_name="studyspot",
            name="venue_wifi",
            field=models.BooleanField(
                blank=True,
                null=True,
                help_text=(
                    "Whether OpenStreetMap records Wi-Fi this venue provides. A different "
                    "claim from free_public_wifi, which is a hotspot the *city* publishes "
                    "within 25 m of the point: a cafe can have its own Wi-Fi and no city "
                    "hotspot anywhere near it, and a library can have the hotspot. Null means "
                    "unrecorded. False is a contributor who went and looked and found none, "
                    "which is a trustworthy negative -- unlike a false free_public_wifi, which "
                    "only ever meant that no published hotspot is nearby."
                ),
            ),
        ),
        migrations.AddField(
            model_name="studyspot",
            name="opening_hours",
            field=models.TextField(
                blank=True,
                null=True,
                help_text=(
                    "When the place is open, in OpenStreetMap's own syntax, as in "
                    "'Mo-Fr 07:00-19:00; Sa-Su 08:00-18:00'. Stored and served as written "
                    "rather than parsed: deciding whether somewhere is open now needs a "
                    "timezone and the public-holiday calendar the syntax can refer to, and "
                    "telling someone a closed cafe is open is worse than telling them "
                    "nothing. Null for every spot no contributor has recorded hours for, "
                    "which is every library -- no city source publishes a schedule."
                ),
            ),
        ),
        migrations.AddIndex(model_name="studyspot", index=INDOOR_SEATING_INDEX),
    ]
