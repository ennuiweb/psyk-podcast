from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("quizzes", "0010_usersubjectlastlecture"),
    ]

    operations = [
        migrations.RenameField(
            model_name="quizprogress",
            old_name="leaderboard_season_key",
            new_name="leaderboard_semester_key",
        ),
    ]
