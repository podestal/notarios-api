import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from notaria.models import Usuarios
from core.models import User

class Command(BaseCommand):
    help = 'Populate attendances for all students'
    def add_arguments(self, parser):
        parser.add_argument(
            '--notary',
            type=int,
            required=True,
            help='Specify the notary ID to create users for'
        )

    def handle(self, *args, **options):

        notary_id = options['notary']
        self.stdout.write(f'Creating users for notary ID: {notary_id}')
        usuarios = Usuarios.objects.all()
        for usuario in usuarios:
            self.stdout.write(f'Creating user: {usuario.prinom} {usuario.apepat}')
            user = User.objects.create_user(
                idusuario=usuario.idusuario,
                username=usuario.loginusuario.lower(),
                password=usuario.password.lower(),
                email=f'{usuario.loginusuario.lower()}@signatum.com',
                first_name=f'{usuario.prinom} {usuario.segnom}',
                last_name=f'{usuario.apepat} {usuario.apemat}',
                notary=notary_id
            )
            self.stdout.write(f'User created: {user.username} with notary level {user.notary}')

        self.stdout.write(self.style.SUCCESS('Users created successfully.'))
