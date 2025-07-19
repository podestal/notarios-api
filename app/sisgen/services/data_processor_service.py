# sisgen_service/services/data_processor_service.py
from typing import Dict, List
import logging
from django.db import connection

logger = logging.getLogger(__name__)

class DataProcessorService:
    def __init__(self):
        self.logger = logger
    
    def process_temp_tables(self, kardex_list: List[str]) -> Dict:
        """Process temporary tables for SISGEN"""
        try:
            # Clear temp tables
            self._clear_temp_tables()
            
            # Insert into sisgen_temp
            self._insert_sisgen_temp(kardex_list)
            
            # Process legal entities
            juridicas = self._process_juridicas()
            
            # Process natural persons
            naturales = self._process_naturales()
            
            # Process interventions
            intervenciones = self._process_intervenciones()
            
            return {
                'juridicas_count': len(juridicas),
                'naturales_count': len(naturales),
                'intervenciones_count': len(intervenciones)
            }
            
        except Exception as e:
            self.logger.error(f"Error processing temp tables: {str(e)}")
            raise
    
    def _clear_temp_tables(self):
        """Clear all temporary tables"""
        tables = ['sisgen_temp', 'sisgen_temp_j', 'sisgen_temp_n', 'sisgen_intervenciones_6']
        
        with connection.cursor() as cursor:
            for table in tables:
                cursor.execute(f"TRUNCATE {table}")
    
    def _insert_sisgen_temp(self, kardex_list: List[str]):
        """Insert data into sisgen_temp table"""
        if not kardex_list:
            return
        
        # This would be populated from the search results
        # Implementation depends on your data structure
        pass
    
    def _process_juridicas(self) -> List[Dict]:
        """Process legal entities"""
        query = """
            SELECT cl.idcontratante, cl.idcliente AS id, cl.tipper AS tipp,
                   cl.idtipdoc AS tipodoc, cl.numdoc AS numdoc, cl.idubigeo,
                   cl.razonsocial AS razonsocial, cl.domfiscal, cl.telempresa AS telempresa,
                   cl.mailempresa AS correoemp, cl.contacempresa AS objeto,
                   cl.fechaconstitu, SUBSTRING(CONCAT('0',cl.idsedereg),1,2) AS sedereg,
                   cl.numregistro, cl.numpartida AS numpartidareg, cl.actmunicipal,
                   cl.residente, cl.docpaisemi, co.idcontratante, co.idtipkar,
                   co.kardex, SUBSTRING(co.condicion,1,3) AS condi, co.firma,
                   co.fechafirma, co.resfirma, co.tiporepresentacion, co.idcontratanterp,
                   co.idsedereg, co.numpartida, co.facultades, co.inscrito,
                   u.coddist AS distrito, u.codprov AS provincia, u.codpto AS departamento,
                   c.coddivi AS ciuu, codtipdoc AS tipodoc, prof.codprof AS profesion,
                   na.codnacion AS nacionalidad, cx.uif AS ROUIF, cl.idcliente AS idcliente
            FROM sisgen_temp
            LEFT JOIN contratantesxacto cx ON sisgen_temp.kardex = cx.kardex
            LEFT JOIN cliente2 cl ON cx.idcontratante = cl.idcontratante
            LEFT JOIN contratantes co ON cl.idcontratante = co.idcontratante
            LEFT JOIN ubigeo u ON cl.idubigeo = u.coddis
            LEFT JOIN ciiu c ON cl.actmunicipal = c.coddivi
            LEFT JOIN tipodocumento td ON cl.idtipdoc = td.idtipdoc
            LEFT JOIN profesiones prof ON cl.idprofesion = prof.idprofesion
            LEFT JOIN nacionalidades na ON cl.nacionalidad = na.idnacionalidad
            WHERE (cx.uif = 'O' OR cx.uif = 'B' OR cx.uif = 'G' OR cx.uif = 'N' OR cx.uif = 'R')
              AND cl.tipper = 'J'
        """
        
        with connection.cursor() as cursor:
            cursor.execute(query)
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def _process_naturales(self) -> List[Dict]:
        """Process natural persons"""
        query = """
            SELECT cl.idcontratante, cl.idcliente AS id, cl.tipper AS tipp,
                   cl.apepat AS apepat, cl.apemat AS apemat,
                   CONCAT(TRIM(cl.prinom),' ',TRIM(cl.segnom)) AS nom,
                   cl.nombre, cl.direccion AS direccion, cl.idtipdoc, cl.numdoc AS numdoc,
                   cl.email AS email, cl.telfijo AS telfijo, cl.telcel, cl.telofi,
                   cl.sexo AS gen, cl.idestcivil AS estc, cl.natper, cl.conyuge,
                   cl.nacionalidad AS naci, cl.idprofesion, cl.detaprofesion,
                   cl.idcargoprofe, cl.profocupa, cl.dirfer, cl.idubigeo,
                   cl.cumpclie AS fechanaci, cl.residente,
                   u.coddist AS distrito, u.codprov AS provincia, u.codpto AS departamento,
                   codtipdoc AS tipodoc, prof.codprof AS profesion,
                   na.codnacion AS nacionalidad, cp.codcargoprofe AS cargo,
                   cx.uif AS ROLUIF, co.kardex AS kardex
            FROM sisgen_temp
            LEFT JOIN contratantesxacto cx ON sisgen_temp.kardex = cx.kardex
            LEFT JOIN cliente2 cl ON cx.idcontratante = cl.idcontratante
            LEFT JOIN contratantes co ON cl.idcontratante = co.idcontratante
            LEFT JOIN ubigeo u ON cl.idubigeo = u.coddis
            LEFT JOIN ciiu c ON cl.actmunicipal = c.coddivi
            LEFT JOIN tipodocumento td ON cl.idtipdoc = td.idtipdoc
            LEFT JOIN profesiones prof ON cl.idprofesion = prof.idprofesion
            LEFT JOIN nacionalidades na ON cl.nacionalidad = na.idnacionalidad
            LEFT JOIN cargoprofe cp ON cl.idcargoprofe = cp.idcargoprofe
            WHERE (cx.uif = 'O' OR cx.uif = 'B' OR cx.uif = 'G' OR cx.uif = 'N' OR cx.uif = 'R')
              AND cl.tipper = 'N'
        """
        
        with connection.cursor() as cursor:
            cursor.execute(query)
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def _process_intervenciones(self) -> List[Dict]:
        """Process interventions"""
        query = """
            SELECT cl.idcontratante AS idcon, cl.idcliente AS idcl, cl.tipper AS tipp,
                   cl.apepat AS apepat, cl.apemat AS apemat,
                   CONCAT(cl.prinom,' ',cl.segnom) AS nom, cl.nombre,
                   cl.direccion AS direccion, cl.idtipdoc AS tipodoc, cl.numdoc AS numdoc,
                   cl.email AS email, cl.telfijo AS telfijo, cl.telcel, cl.telofi,
                   cl.sexo AS gen, cl.idestcivil AS estc, cl.natper, cl.conyuge AS conyuge,
                   cl.nacionalidad AS nacionalidad, cl.idprofesion AS profesion,
                   cl.detaprofesion, cl.idcargoprofe AS cargo, cl.profocupa, cl.dirfer,
                   cl.idubigeo, cl.cumpclie AS fechanaci, cl.fechaing,
                   cl.razonsocial AS razonsocial, cl.domfiscal, cl.telempresa AS telempresa,
                   cl.mailempresa AS correoemp, cl.contacempresa, cl.fechaconstitu,
                   cl.idsedereg, cl.numregistro, cl.numpartida AS numpartida,
                   cl.actmunicipal, cl.tipocli, cl.impeingre, cl.impnumof, cl.impeorigen,
                   cl.impentidad, cl.impremite, cl.impmotivo, cl.residente, cl.docpaisemi,
                   co.idcontratante, co.idtipkar, co.kardex, co.firma, co.fechafirma AS ffirma,
                   co.resfirma, co.tiporepresentacion, co.idcontratanterp, co.idsedereg,
                   co.numpartida, co.facultades, co.indice, co.visita, co.inscrito,
                   SUBSTRING(co.condicion,1,3) AS condi, act.condicion AS condicionn,
                   act.codconsisgen AS condicionnsisgen, cxa.id, cxa.idtipkar, cxa.kardex,
                   cxa.idtipoacto, cxa.idcontratante, cxa.item, cxa.idcondicion,
                   act.parte AS parte, cxa.porcentaje, cxa.uif AS repre, cxa.formulario,
                   cxa.monto AS montoo, cxa.opago, cxa.ofondo AS fondos, cxa.montop
            FROM sisgen_temp
            INNER JOIN contratantesxacto cxa ON sisgen_temp.kardex = cxa.kardex
            INNER JOIN cliente2 cl ON cl.idcontratante = cxa.idcontratante
            LEFT JOIN contratantes co ON cxa.idcontratante = co.idcontratante
            LEFT JOIN actocondicion act ON act.idcondicion = cxa.idcondicion
        """
        
        with connection.cursor() as cursor:
            cursor.execute(query)
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]