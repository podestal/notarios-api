from django.db import migrations
import logging

logger = logging.getLogger(__name__)

def normalize_db_schema(apps, schema_editor):
    """
    Safely normalize database schema by adding missing fields based on Django models.
    This migration is non-intrusive and only adds fields when necessary.
    """
    # Skip if not MySQL
    if schema_editor.connection.vendor != 'mysql':
        return

    # Define all tables and their required fields based on Django models
    # Format: {table_name: {field_name: field_definition}}
    schema_requirements = {
        'tipodocumento': {
            'idtipdoc': 'INT AUTO_INCREMENT PRIMARY KEY',
            'codtipdoc': 'VARCHAR(3)',
            'destipdoc': 'VARCHAR(50)',
            'td_abrev': 'VARCHAR(10) NULL',
            'sunat': 'INT NULL'
        },
        'tipoestacivil': {
            'idestcivil': 'INT AUTO_INCREMENT PRIMARY KEY',
            'codestcivil': 'VARCHAR(2)',
            'desestcivil': 'VARCHAR(50)'
        },
        'usuarios': {
            'idusuario': 'INT AUTO_INCREMENT PRIMARY KEY',
            'loginusuario': 'VARCHAR(50)',
            'password': 'VARCHAR(50)',
            'apepat': 'VARCHAR(100)',
            'apemat': 'VARCHAR(100)',
            'prinom': 'VARCHAR(100)',
            'segnom': 'VARCHAR(100)',
            'fecnac': 'VARCHAR(10)',
            'estado': 'INT',
            'domicilio': 'VARCHAR(100)',
            'idubigeo': 'INT',
            'telefono': 'VARCHAR(30)',
            'idcargo': 'INT',
            'dni': 'VARCHAR(8) NULL'
        },
        'permisos_usuarios': {
            'idusuario': 'VARCHAR(9) PRIMARY KEY',
            'kardex': 'VARCHAR(30) NULL',
            'newkar': 'VARCHAR(1) NULL',
            'editkar': 'VARCHAR(1) NULL',
            'protesto': 'VARCHAR(1) NULL',
            'newprot': 'VARCHAR(1) NULL',
            'editprot': 'VARCHAR(1) NULL',
            'pviaje': 'VARCHAR(1) NULL',
            'newvia': 'VARCHAR(1) NULL',
            'editvia': 'VARCHAR(1) NULL',
            'poder': 'VARCHAR(1) NULL',
            'newpod': 'VARCHAR(1) NULL',
            'editpod': 'VARCHAR(1) NULL',
            'cartas': 'VARCHAR(1) NULL',
            'newcar': 'VARCHAR(1) NULL',
            'editcar': 'VARCHAR(1) NULL',
            'libros': 'VARCHAR(1) NULL',
            'newlib': 'VARCHAR(1) NULL',
            'editlib': 'VARCHAR(1) NULL',
            'capaz': 'VARCHAR(1) NULL',
            'newcap': 'VARCHAR(1) NULL',
            'editcap': 'VARCHAR(1) NULL',
            'incapaz': 'VARCHAR(1) NULL',
            'newinca': 'VARCHAR(1) NULL',
            'editinca': 'VARCHAR(1) NULL',
            'domiciliario': 'VARCHAR(1) NULL',
            'newdom': 'VARCHAR(1) NULL',
            'editdom': 'VARCHAR(1) NULL',
            'caracteristicas': 'VARCHAR(1) NULL',
            'newcarac': 'VARCHAR(1) NULL',
            'editcarac': 'VARCHAR(1) NULL',
            'indicronoep': 'VARCHAR(1) NULL',
            'indicrononc': 'VARCHAR(1) NULL',
            'indicronotv': 'VARCHAR(1) NULL',
            'indicronogm': 'VARCHAR(1) NULL',
            'indicronotest': 'VARCHAR(1) NULL',
            'indicronoprot': 'VARCHAR(1) NULL',
            'infocamacome': 'VARCHAR(1) NULL',
            'indicronocar': 'VARCHAR(1) NULL',
            'indicronolib': 'VARCHAR(1) NULL',
            'indicronovia': 'VARCHAR(1) NULL',
            'indicronopod': 'VARCHAR(1) NULL'
        },
        'kardex': {
            'kardex': 'VARCHAR(30) PRIMARY KEY',
            'idtipkar': 'INT',
            'fechaescritura': 'DATE',
            'numescritura': 'VARCHAR(20)',
            'idnotario': 'INT',
            'idtipdoc': 'INT',
            'numdoc': 'VARCHAR(20)',
            'fechadoc': 'DATE',
            'idubigeo': 'INT',
            'direccion': 'VARCHAR(200)',
            'observaciones': 'TEXT',
            'estado': 'INT',
            'fechacreacion': 'DATETIME',
            'fechamodificacion': 'DATETIME',
            'usuariocreacion': 'VARCHAR(50)',
            'usuariomodificacion': 'VARCHAR(50)',
            'ipcreacion': 'VARCHAR(15)',
            'ipmodificacion': 'VARCHAR(15)',
            'idtipacto': 'INT',
            'idactocondicion': 'INT',
            'idestado': 'INT',
            'idtipofolio': 'INT',
            'idtipolibro': 'INT',
            'idnlibro': 'INT',
            'folio': 'INT',
            'responsable_new': 'VARCHAR(3000) NULL',
            'fechaminuta': 'VARCHAR(15) NULL',
            'ob_nota': 'VARCHAR(6000) NULL',
            'ins_espec': 'VARCHAR(6000) NULL',
            'recepcion': 'VARCHAR(30) NULL',
            'funcionario_new': 'VARCHAR(3000) NULL',
            'nc': 'VARCHAR(30) NULL',
            'fecha_modificacion': 'VARCHAR(10) NULL',
            'idpresentante': 'INT NULL',
            'papeltrasladoini': 'VARCHAR(30) NULL',
            'papeltrasladofin': 'VARCHAR(30) NULL',
            'fktemplate': 'INT NULL',
            'estado_sisgen': 'INT NULL'
        },
        'tipokar': {
            'idtipkar': 'INT AUTO_INCREMENT PRIMARY KEY',
            'nomtipkar': 'VARCHAR(50)',
            'tipkar': 'VARCHAR(1)'
        },
        'contratantes': {
            'idcontratante': 'VARCHAR(10) PRIMARY KEY',
            'idtipkar': 'INT',
            'kardex': 'VARCHAR(30) NULL',
            'condicion': 'VARCHAR(100)',
            'firma': 'VARCHAR(3)',
            'fechafirma': 'VARCHAR(10) NULL',
            'resfirma': 'INT',
            'tiporepresentacion': 'VARCHAR(2)',
            'idcontratanterp': 'VARCHAR(3000) NULL',
            'idsedereg': 'VARCHAR(3) NULL',
            'numpartida': 'VARCHAR(50) NULL',
            'facultades': 'VARCHAR(500)',
            'indice': 'VARCHAR(3)',
            'visita': 'VARCHAR(3)',
            'inscrito': 'VARCHAR(1) NULL',
            'plantilla': 'VARCHAR(3) NULL'
        },
        'contratantesxacto': {
            'id': 'INT AUTO_INCREMENT PRIMARY KEY',
            'idtipkar': 'INT',
            'kardex': 'VARCHAR(30) NULL',
            'idtipoacto': 'VARCHAR(6)',
            'idcontratante': 'VARCHAR(10)',
            'item': 'INT',
            'idcondicion': 'VARCHAR(3)',
            'parte': 'VARCHAR(3)',
            'porcentaje': 'VARCHAR(50)',
            'uif': 'VARCHAR(5)',
            'formulario': 'VARCHAR(2)',
            'monto': 'VARCHAR(100)',
            'opago': 'VARCHAR(2)',
            'ofondo': 'VARCHAR(300)',
            'montop': 'VARCHAR(2)'
        },
        'cliente': {
            'idcliente': 'VARCHAR(10) PRIMARY KEY',
            'tipper': 'VARCHAR(1) NULL',
            'apepat': 'VARCHAR(100) NULL',
            'apemat': 'VARCHAR(100) NULL',
            'prinom': 'VARCHAR(100) NULL',
            'segnom': 'VARCHAR(100) NULL',
            'nombre': 'VARCHAR(1000) NULL',
            'direccion': 'VARCHAR(3000) NULL',
            'idtipdoc': 'INT NULL',
            'numdoc': 'VARCHAR(50) NULL',
            'email': 'VARCHAR(300) NULL',
            'telfijo': 'VARCHAR(20) NULL',
            'telcel': 'VARCHAR(20) NULL',
            'telofi': 'VARCHAR(20) NULL',
            'sexo': 'VARCHAR(1) NULL',
            'idestcivil': 'INT NULL',
            'natper': 'VARCHAR(50) NULL',
            'conyuge': 'VARCHAR(10) NULL',
            'nacionalidad': 'VARCHAR(100) NULL',
            'idprofesion': 'INT NULL',
            'detaprofesion': 'VARCHAR(1000) NULL',
            'idcargoprofe': 'INT NULL',
            'profocupa': 'VARCHAR(1000) NULL',
            'dirfer': 'VARCHAR(300) NULL',
            'idubigeo': 'VARCHAR(6)',
            'cumpclie': 'VARCHAR(15)',
            'fechaing': 'VARCHAR(10) NULL',
            'razonsocial': 'VARCHAR(3000) NULL',
            'domfiscal': 'VARCHAR(3000) NULL',
            'telempresa': 'VARCHAR(12) NULL',
            'mailempresa': 'VARCHAR(200) NULL',
            'contacempresa': 'VARCHAR(3000) NULL',
            'fechaconstitu': 'VARCHAR(12) NULL',
            'idsedereg': 'INT',
            'numregistro': 'VARCHAR(50) NULL',
            'numpartida': 'VARCHAR(50) NULL',
            'actmunicipal': 'VARCHAR(3000) NULL',
            'tipocli': 'VARCHAR(1) NULL',
            'impeingre': 'VARCHAR(10) NULL',
            'impnumof': 'VARCHAR(50) NULL',
            'impeorigen': 'VARCHAR(3000) NULL',
            'impentidad': 'VARCHAR(3000) NULL',
            'impremite': 'VARCHAR(3000) NULL',
            'impmotivo': 'VARCHAR(3000) NULL',
            'residente': 'VARCHAR(2) NULL',
            'docpaisemi': 'VARCHAR(100) NULL',
            'partidaconyuge': 'VARCHAR(15) NULL',
            'separaciondebienes': 'VARCHAR(1) NULL',
            'idsedeconyuge': 'VARCHAR(11) NULL',
            'numdoc_plantilla': 'VARCHAR(11) NULL',
            'profesion_plantilla': 'VARCHAR(200) NULL',
            'ubigeo_plantilla': 'VARCHAR(100) NULL'
        },
        'cliente2': {
            'idcontratante': 'VARCHAR(10) PRIMARY KEY',
            'idcliente': 'VARCHAR(10)',
            'tipper': 'VARCHAR(1)',
            'apepat': 'VARCHAR(100) NULL',
            'apemat': 'VARCHAR(100) NULL',
            'prinom': 'VARCHAR(100) NULL',
            'segnom': 'VARCHAR(100) NULL',
            'nombre': 'VARCHAR(1000) NULL',
            'direccion': 'VARCHAR(3000) NULL',
            'idtipdoc': 'INT',
            'numdoc': 'VARCHAR(50) NULL',
            'email': 'VARCHAR(300) NULL',
            'telfijo': 'VARCHAR(20) NULL',
            'telcel': 'VARCHAR(20) NULL',
            'telofi': 'VARCHAR(20) NULL',
            'sexo': 'VARCHAR(1) NULL',
            'idestcivil': 'INT',
            'natper': 'VARCHAR(50) NULL',
            'conyuge': 'VARCHAR(10) NULL',
            'nacionalidad': 'VARCHAR(100) NULL',
            'idprofesion': 'INT NULL',
            'detaprofesion': 'VARCHAR(1000) NULL',
            'idcargoprofe': 'INT NULL',
            'profocupa': 'VARCHAR(1000) NULL',
            'dirfer': 'VARCHAR(300) NULL',
            'idubigeo': 'VARCHAR(6)',
            'cumpclie': 'VARCHAR(15)',
            'fechaing': 'VARCHAR(10) NULL',
            'razonsocial': 'VARCHAR(3000) NULL',
            'domfiscal': 'VARCHAR(3000) NULL',
            'telempresa': 'VARCHAR(12) NULL',
            'mailempresa': 'VARCHAR(200) NULL',
            'contacempresa': 'VARCHAR(3000) NULL',
            'fechaconstitu': 'VARCHAR(12) NULL',
            'idsedereg': 'INT',
            'numregistro': 'VARCHAR(50) NULL',
            'numpartida': 'VARCHAR(50) NULL',
            'actmunicipal': 'VARCHAR(3000) NULL',
            'tipocli': 'VARCHAR(1) NULL',
            'impeingre': 'VARCHAR(10) NULL',
            'impnumof': 'VARCHAR(50) NULL',
            'impeorigen': 'VARCHAR(3000) NULL',
            'impentidad': 'VARCHAR(3000) NULL',
            'impremite': 'VARCHAR(3000) NULL',
            'impmotivo': 'VARCHAR(3000) NULL',
            'residente': 'VARCHAR(2)',
            'docpaisemi': 'VARCHAR(100) NULL',
            'partidaconyuge': 'VARCHAR(15) NULL',
            'separaciondebienes': 'VARCHAR(1) NULL',
            'idsedeconyuge': 'VARCHAR(11) NULL',
            'profesion_plantilla': 'VARCHAR(200) NULL',
            'ubigeo_plantilla': 'VARCHAR(100) NULL'
        },
        'tiposdeacto': {
            'idtipoacto': 'VARCHAR(6) PRIMARY KEY',
            'actosunat': 'VARCHAR(25) NULL',
            'actouif': 'VARCHAR(25) NULL',
            'idtipkar': 'INT',
            'desacto': 'VARCHAR(300)',
            'umbral': 'INT NULL',
            'impuestos': 'INT NULL',
            'idcalnot': 'INT NULL',
            'idecalreg': 'INT NULL',
            'idmodelo': 'INT NULL',
            'rol_part': 'VARCHAR(10) NULL',
            'cod_ancert': 'VARCHAR(5) NULL',
            'tipoplantilla_default': 'VARCHAR(1) NULL'
        },
        'actocondicion': {
            'idcondicion': 'INT AUTO_INCREMENT PRIMARY KEY',
            'condicion': 'VARCHAR(100)',
            'codconsisgen': 'VARCHAR(10)',
            'parte': 'VARCHAR(50)'
        },
        'detalle_actos_kardex': {
            'id': 'INT AUTO_INCREMENT PRIMARY KEY',
            'kardex': 'VARCHAR(30)',
            'idtipacto': 'INT',
            'idcondicion': 'INT',
            'parte': 'VARCHAR(50)',
            'porcentaje': 'DECIMAL(5,2)',
            'monto': 'DECIMAL(10,2)',
            'opago': 'VARCHAR(50)',
            'ofondo': 'VARCHAR(50)',
            'montop': 'DECIMAL(10,2)'
        },
        'tb_abogado': {
            'idabogado': 'INT AUTO_INCREMENT PRIMARY KEY',
            'codabogado': 'VARCHAR(10)',
            'nombre': 'VARCHAR(200)',
            'direccion': 'VARCHAR(200)',
            'telefono': 'VARCHAR(20)',
            'email': 'VARCHAR(100)',
            'estado': 'VARCHAR(1)'
        },
        'nacionalidades': {
            'idnacionalidad': 'INT AUTO_INCREMENT PRIMARY KEY',
            'codnacion': 'VARCHAR(3)',
            'desnacion': 'VARCHAR(100)'
        },
        'profesiones': {
            'idprofesion': 'INT AUTO_INCREMENT PRIMARY KEY',
            'codprof': 'VARCHAR(10)',
            'desprof': 'VARCHAR(100)'
        },
        'cargoprofe': {
            'idcargoprofe': 'INT AUTO_INCREMENT PRIMARY KEY',
            'codcargoprofe': 'VARCHAR(10)',
            'descargoprofe': 'VARCHAR(100)'
        },
        'ubigeo': {
            'coddis': 'INT PRIMARY KEY',
            'coddist': 'VARCHAR(6)',
            'codprov': 'VARCHAR(4)',
            'codpto': 'VARCHAR(2)',
            'desdist': 'VARCHAR(100)',
            'desprov': 'VARCHAR(100)',
            'despto': 'VARCHAR(100)'
        },
        'sedesregistrales': {
            'idsedereg': 'INT AUTO_INCREMENT PRIMARY KEY',
            'codsedereg': 'VARCHAR(10)',
            'dessedereg': 'VARCHAR(100)',
            'direccion': 'VARCHAR(200)',
            'telefono': 'VARCHAR(20)',
            'estado': 'VARCHAR(1)'
        },
        'representantes': {
            'idrepresentante': 'INT AUTO_INCREMENT PRIMARY KEY',
            'idcontratante': 'VARCHAR(10)',
            'idtipkar': 'INT',
            'kardex': 'VARCHAR(30)',
            'tiporepresentacion': 'VARCHAR(50)',
            'facultades': 'TEXT',
            'fechainicio': 'DATE',
            'fechafin': 'DATE',
            'estado': 'VARCHAR(1)'
        },
        'patrimonial': {
            'idpatrimonial': 'INT AUTO_INCREMENT PRIMARY KEY',
            'idcontratante': 'VARCHAR(10)',
            'idtipkar': 'INT',
            'kardex': 'VARCHAR(30)',
            'tipobien': 'VARCHAR(50)',
            'descripcion': 'TEXT',
            'valor': 'DECIMAL(10,2)',
            'estado': 'VARCHAR(1)'
        },
        'detallevehicular': {
            'iddetallevehicular': 'INT AUTO_INCREMENT PRIMARY KEY',
            'idcontratante': 'VARCHAR(10)',
            'idtipkar': 'INT',
            'kardex': 'VARCHAR(30)',
            'placa': 'VARCHAR(10)',
            'marca': 'VARCHAR(50)',
            'modelo': 'VARCHAR(50)',
            'anio': 'INT',
            'color': 'VARCHAR(30)',
            'motor': 'VARCHAR(20)',
            'serie': 'VARCHAR(20)',
            'estado': 'VARCHAR(1)'
        },
        'detallebienes': {
            'iddetallebienes': 'INT AUTO_INCREMENT PRIMARY KEY',
            'idcontratante': 'VARCHAR(10)',
            'idtipkar': 'INT',
            'kardex': 'VARCHAR(30)',
            'tipobien': 'VARCHAR(50)',
            'descripcion': 'TEXT',
            'valor': 'DECIMAL(10,2)',
            'estado': 'VARCHAR(1)'
        },
        'detallemediopago': {
            'iddetallemediopago': 'INT AUTO_INCREMENT PRIMARY KEY',
            'idcontratante': 'VARCHAR(10)',
            'idtipkar': 'INT',
            'kardex': 'VARCHAR(30)',
            'tipomediopago': 'VARCHAR(50)',
            'descripcion': 'TEXT',
            'monto': 'DECIMAL(10,2)',
            'estado': 'VARCHAR(1)'
        },
        'predios': {
            'idpredio': 'INT AUTO_INCREMENT PRIMARY KEY',
            'idcontratante': 'VARCHAR(10)',
            'idtipkar': 'INT',
            'kardex': 'VARCHAR(30)',
            'direccion': 'VARCHAR(200)',
            'area': 'DECIMAL(10,2)',
            'valor': 'DECIMAL(10,2)',
            'estado': 'VARCHAR(1)'
        },
        'tpl_template': {
            'idtemplate': 'INT AUTO_INCREMENT PRIMARY KEY',
            'nombretemplate': 'VARCHAR(100)',
            'descripcion': 'TEXT',
            'contenido': 'LONGTEXT',
            'estado': 'VARCHAR(1)'
        },
        'legalizacion': {
            'idlegalizacion': 'INT AUTO_INCREMENT PRIMARY KEY',
            'idtipkar': 'INT',
            'kardex': 'VARCHAR(30)',
            'fechalegalizacion': 'DATE',
            'observaciones': 'TEXT',
            'estado': 'VARCHAR(1)'
        },
        'permi_viaje': {
            'idpermivi': 'INT AUTO_INCREMENT PRIMARY KEY',
            'idtipkar': 'INT',
            'kardex': 'VARCHAR(30)',
            'fechasolicitud': 'DATE',
            'fechaaprobacion': 'DATE',
            'estado': 'VARCHAR(1)',
            'observaciones': 'TEXT',
            'via': 'VARCHAR(255) NULL',
            'fecha_desde': 'DATE NULL',
            'fecha_hasta': 'DATE NULL'
        },
        'viaje_contratantes': {
            'idviajecontratante': 'INT AUTO_INCREMENT PRIMARY KEY',
            'idpermivi': 'INT',
            'idcontratante': 'VARCHAR(10)',
            'tipoviaje': 'VARCHAR(50)',
            'estado': 'VARCHAR(1)'
        },
        'ingreso_poderes': {
            'idingresopoder': 'INT AUTO_INCREMENT PRIMARY KEY',
            'idtipkar': 'INT',
            'kardex': 'VARCHAR(30)',
            'fechaingreso': 'DATE',
            'estado': 'VARCHAR(1)',
            'observaciones': 'TEXT'
        },
        'poderes_fuerareg': {
            'idpoderfuerareg': 'INT AUTO_INCREMENT PRIMARY KEY',
            'idingresopoder': 'INT',
            'tipopoder': 'VARCHAR(50)',
            'estado': 'VARCHAR(1)',
            'observaciones': 'TEXT'
        },
        'poderes_pension': {
            'idpoderpension': 'INT AUTO_INCREMENT PRIMARY KEY',
            'idingresopoder': 'INT',
            'tipopension': 'VARCHAR(50)',
            'estado': 'VARCHAR(1)',
            'observaciones': 'TEXT'
        },
        'poderes_contratantes': {
            'idpodercontratante': 'INT AUTO_INCREMENT PRIMARY KEY',
            'idingresopoder': 'INT',
            'idcontratante': 'VARCHAR(10)',
            'tipopoder': 'VARCHAR(50)',
            'estado': 'VARCHAR(1)',
            'observaciones': 'TEXT'
        },
        'ingreso_cartas': {
            'idingresocarta': 'INT AUTO_INCREMENT PRIMARY KEY',
            'idtipkar': 'INT',
            'kardex': 'VARCHAR(30)',
            'fechaingreso': 'DATE',
            'estado': 'VARCHAR(1)',
            'observaciones': 'TEXT',
            'dni_destinatario': 'VARCHAR(8) NULL',
            'recepcion': 'VARCHAR(250) NULL'
        },
        'libros': {
            'idlibro': 'INT AUTO_INCREMENT PRIMARY KEY',
            'numlibro': 'VARCHAR(10)',
            'ano': 'VARCHAR(4)',
            'fecing': 'DATE',
            'tipper': 'VARCHAR(1) NULL',
            'apepat': 'VARCHAR(1000) NULL',
            'apemat': 'VARCHAR(1000) NULL',
            'prinom': 'VARCHAR(1000) NULL',
            'segnom': 'VARCHAR(1000) NULL',
            'ruc': 'VARCHAR(11) NULL',
            'domicilio': 'VARCHAR(2000) NULL',
            'coddis': 'VARCHAR(6) NULL',
            'empresa': 'VARCHAR(5000) NULL',
            'domfiscal': 'VARCHAR(3000) NULL',
            'idtiplib': 'INT NULL',
            'descritiplib': 'VARCHAR(3000) NULL',
            'idlegal': 'INT NULL',
            'folio': 'VARCHAR(20) NULL',
            'idtipfol': 'INT NULL',
            'detalle': 'VARCHAR(3000) NULL',
            'idnotario': 'INT NULL',
            'solicitante': 'VARCHAR(3000) NULL',
            'comentario': 'VARCHAR(3000) NULL',
            'feclegal': 'VARCHAR(12) NULL',
            'comentario2': 'VARCHAR(3000) NULL',
            'dni': 'VARCHAR(11) NULL',
            'idusuario': 'INT NULL',
            'idnlibro': 'INT NULL',
            'codclie': 'VARCHAR(10) NULL',
            'flag': 'INT NULL',
            'numdoc_plantilla': 'VARCHAR(11) NULL',
            'estadosisgen': 'INT NULL'
        },
        'nlibro': {
            'idnlibro': 'INT AUTO_INCREMENT PRIMARY KEY',
            'desnlibro': 'VARCHAR(300)',
            'numlibro': 'VARCHAR(3) NULL'
        },
        'tipofolio': {
            'idtipfol': 'INT',
            'destipfol': 'VARCHAR(50)'
        },
        'tipolibro': {
            'idtiplib': 'INT PRIMARY KEY',
            'coddlib': 'VARCHAR(2)',
            'destiplib': 'VARCHAR(50)'
        },
        'cert_domiciliario': {
            'id_domiciliario': 'INT AUTO_INCREMENT PRIMARY KEY',
            'num_certificado': 'VARCHAR(10) NULL',
            'fec_ingreso': 'VARCHAR(20) NULL',
            'num_formu': 'VARCHAR(30) NULL',
            'nombre_solic': 'VARCHAR(500) NULL',
            'tipdoc_solic': 'VARCHAR(20) NULL',
            'numdoc_solic': 'VARCHAR(50) NULL',
            'domic_solic': 'VARCHAR(3000) NULL',
            'motivo_solic': 'VARCHAR(3000) NULL',
            'distrito_solic': 'VARCHAR(50) NULL',
            'texto_cuerpo': 'TEXT NULL',
            'justifi_cuerpo': 'TEXT NULL',
            'nom_testigo': 'VARCHAR(500) NULL',
            'recibo_empresa': 'VARCHAR(200) NULL',
            'fecha_ocupa': 'DATE NULL',
            'declara_ser': 'VARCHAR(200) NULL',
            'propietario': 'VARCHAR(200) NULL',
            'recibido': 'VARCHAR(200) NULL',
            'numero_recibo': 'VARCHAR(60) NULL',
            'mes_facturado': 'VARCHAR(60) NULL'
        }
    }

    with schema_editor.connection.cursor() as cursor:
        for table_name, fields in schema_requirements.items():
            try:
                # Check if table exists
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    WHERE table_schema = DATABASE()
                    AND table_name = %s
                """, [table_name])
                
                if cursor.fetchone()[0] == 0:
                    # Table doesn't exist, skip it
                    logger.info(f"Table {table_name} doesn't exist, skipping")
                    continue
                
                # Get existing columns for this table
                cursor.execute("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = DATABASE()
                    AND table_name = %s
                """, [table_name])
                
                existing_columns = {row[0] for row in cursor.fetchall()}
                
                # Add missing fields
                for field_name, field_definition in fields.items():
                    if field_name not in existing_columns:
                        try:
                            # Extract just the field type for ALTER TABLE
                            field_type = field_definition.split()[0]
                            if 'AUTO_INCREMENT' in field_definition:
                                field_type = 'INT'
                            
                            # Handle special cases
                            if 'PRIMARY KEY' in field_definition:
                                # Skip primary key fields as they should already exist
                                continue
                            
                            # Add the field
                            cursor.execute(f"""
                                ALTER TABLE {table_name}
                                ADD COLUMN {field_name} {field_type} NULL
                            """)
                            
                            logger.info(f"Added field {field_name} to table {table_name}")
                            
                        except Exception as e:
                            # Log error but continue with other fields
                            logger.warning(f"Failed to add field {field_name} to table {table_name}: {str(e)}")
                            continue
                            
            except Exception as e:
                # Log error but continue with other tables
                logger.error(f"Error processing table {table_name}: {str(e)}")
                continue


def reverse_migration(apps, schema_editor):
    """
    Reverse migration - this is complex to implement safely,
    so we'll just log that it cannot be automatically reversed.
    """
    logger.info("Schema normalization migration cannot be automatically reversed")


class Migration(migrations.Migration):
    dependencies = [
        # This is the initial migration for the notaria app
    ]

    operations = [
        migrations.RunPython(
            normalize_db_schema,
            reverse_migration
        )
    ] 