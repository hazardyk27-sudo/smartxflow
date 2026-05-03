#!/usr/bin/env python3
"""Bulk-translate all empty (en/de/fr/nl/it/es) entries in master CSV.

Strategy: hand-curated TR -> 6-lang dictionary keyed by exact TR text.
For entries where the TR text is purely a fragment / structural / brand-only,
we copy the TR text verbatim into all 6 languages (universal across langs).
"""
from __future__ import annotations
import csv, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTER = os.path.join(ROOT, 'static/i18n/_master.csv')
LANGS = ['en','de','fr','nl','it','es']
FIELDS = ['key','file_refs','tr'] + LANGS

# Translations table: tr -> {lang: text}.
# Each row gives 6 translations in order: en, de, fr, nl, it, es.
T: dict[str, tuple[str,str,str,str,str,str]] = {
  '10 dakika':         ('10 minutes','10 Minuten','10 minutes','10 minuten','10 minuti','10 minutos'),
  '12 saat':           ('12 hours','12 Stunden','12 heures','12 uur','12 ore','12 horas'),
  '1 saat':            ('1 hour','1 Stunde','1 heure','1 uur','1 ora','1 hora'),
  '30 dakika':         ('30 minutes','30 Minuten','30 minutes','30 minuten','30 minuti','30 minutos'),
  '6 saat':            ('6 hours','6 Stunden','6 heures','6 uur','6 ore','6 horas'),
  'A/Ü 2.5':           ('O/U 2.5','U/Ü 2.5','P/I 2.5','O/U 2.5','O/U 2.5','M/M 2.5'),
  'Açılış → Güncel':   ('Opening → Current','Eröffnung → Aktuell','Ouverture → Actuel','Opening → Huidig','Apertura → Attuale','Apertura → Actual'),
  '1X2 için max açılış oranı (varsayılan: 5.0)':
    ('Max opening odds for 1X2 (default: 5.0)','Max. Eröffnungsquote für 1X2 (Standard: 5.0)','Cote d\'ouverture max pour 1X2 (défaut : 5,0)','Max openingsquote voor 1X2 (standaard: 5.0)','Quota di apertura max per 1X2 (predefinito: 5,0)','Cuota máxima de apertura para 1X2 (por defecto: 5,0)'),
  'Alt/Üst için max açılış oranı (varsayılan: 3.0)':
    ('Max opening odds for Over/Under (default: 3.0)','Max. Eröffnungsquote für Über/Unter (Standard: 3.0)','Cote d\'ouverture max pour Plus/Moins (défaut : 3,0)','Max openingsquote voor Over/Under (standaard: 3.0)','Quota di apertura max per Over/Under (predefinito: 3,0)','Cuota máxima de apertura para Más/Menos (por defecto: 3,0)'),
  'BTTS için max açılış oranı (varsayılan: 3.0)':
    ('Max opening odds for BTTS (default: 3.0)','Max. Eröffnungsquote für BTTS (Standard: 3.0)','Cote d\'ouverture max pour BTTS (défaut : 3,0)','Max openingsquote voor BTTS (standaard: 3.0)','Quota di apertura max per BTTS (predefinito: 3,0)','Cuota máxima de apertura para BTTS (por defecto: 3,0)'),
  '\n                    Açılış oranı bu eşiklerin üzerindeyse dropping alarmı tetiklenmez.\n                ':
    ('\n                    If opening odds are above these thresholds, the dropping alarm will not trigger.\n                ',
     '\n                    Wenn die Eröffnungsquote über diesen Schwellenwerten liegt, wird der Dropping-Alarm nicht ausgelöst.\n                ',
     '\n                    Si la cote d\'ouverture dépasse ces seuils, l\'alarme de baisse ne se déclenche pas.\n                ',
     '\n                    Als de openingsquote boven deze drempels ligt, wordt het dropping-alarm niet geactiveerd.\n                ',
     '\n                    Se la quota di apertura supera queste soglie, l\'allarme di calo non si attiva.\n                ',
     '\n                    Si la cuota de apertura supera estos umbrales, la alarma de caída no se activará.\n                '),
  ' alarm) ---\n':       (' alarms) ---\n',' Alarme) ---\n',' alarmes) ---\n',' alarmen) ---\n',' allarmi) ---\n',' alarmas) ---\n'),
  'Alarm yukleme hatasi:':('Alarm load error:','Alarmladefehler:','Erreur de chargement d\'alarme :','Alarmlaadfout:','Errore caricamento allarme:','Error al cargar alarma:'),
  'Alarm Zamanı':       ('Alarm Time','Alarmzeit','Heure de l\'alarme','Alarmtijd','Orario allarme','Hora de alarma'),
  'Alarmlar yukleniyor...':('Loading alarms...','Alarme werden geladen...','Chargement des alarmes...','Alarmen laden...','Caricamento allarmi...','Cargando alarmas...'),
  '🗑️ Alarmları Sil':    ('🗑️ Delete Alarms','🗑️ Alarme löschen','🗑️ Supprimer les alarmes','🗑️ Alarmen verwijderen','🗑️ Elimina allarmi','🗑️ Eliminar alarmas'),
  '[AutoRefresh] Tab aktif - interval yeniden başlatıldı (jitter: ':
    ('[AutoRefresh] Tab active - interval restarted (jitter: ',
     '[AutoRefresh] Tab aktiv - Intervall neu gestartet (Jitter: ',
     '[AutoRefresh] Onglet actif - intervalle redémarré (gigue : ',
     '[AutoRefresh] Tab actief - interval opnieuw gestart (jitter: ',
     '[AutoRefresh] Scheda attiva - intervallo riavviato (jitter: ',
     '[AutoRefresh] Pestaña activa - intervalo reiniciado (jitter: '),
  '💾 Ayarları Kaydet':  ('💾 Save Settings','💾 Einstellungen speichern','💾 Enregistrer les paramètres','💾 Instellingen opslaan','💾 Salva impostazioni','💾 Guardar ajustes'),
  'Bağlantı hatası':    ('Connection error','Verbindungsfehler','Erreur de connexion','Verbindingsfout','Errore di connessione','Error de conexión'),
  'Batch alarm fetch failed':('Batch alarm fetch failed','Batch-Alarmabruf fehlgeschlagen','Échec de la récupération des alarmes par lots','Batch-alarmophalen mislukt','Recupero allarmi batch fallito','Error al obtener alarmas por lotes'),
  '  Bu mac icin alarm verisi bulunamadi.\n':
    ('  No alarm data found for this match.\n','  Keine Alarmdaten für dieses Spiel gefunden.\n','  Aucune donnée d\'alarme trouvée pour ce match.\n','  Geen alarmgegevens gevonden voor deze wedstrijd.\n','  Nessun dato di allarme trovato per questa partita.\n','  No se encontraron datos de alarma para este partido.\n'),
  "Bu market için veri bulunamadı. Scraper'ın Supabase'e veri gönderdiğinden emin olun.":
    ("No data found for this market. Make sure the scraper is sending data to Supabase.",
     "Keine Daten für diesen Markt gefunden. Stellen Sie sicher, dass der Scraper Daten an Supabase sendet.",
     "Aucune donnée trouvée pour ce marché. Assurez-vous que le scraper envoie des données à Supabase.",
     "Geen gegevens gevonden voor deze markt. Zorg dat de scraper gegevens naar Supabase verzendt.",
     "Nessun dato trovato per questo mercato. Assicurati che lo scraper stia inviando dati a Supabase.",
     "No se encontraron datos para este mercado. Asegúrate de que el scraper envíe datos a Supabase."),
  'Bu seçenekte 10 dk içinde yüksek hacimli para + oran düşüşü tespit edildi.':
    ('High-volume money + odds drop detected on this selection within 10 minutes.',
     'In dieser Auswahl wurde innerhalb von 10 Minuten ein hohes Geld- und Quotenabfall festgestellt.',
     'Volume élevé d\'argent + baisse de cote détectés sur cette sélection en 10 minutes.',
     'Hoge geldvolume + odds-daling gedetecteerd op deze selectie binnen 10 minuten.',
     'Alto volume di denaro + calo quote rilevato su questa selezione entro 10 minuti.',
     'Se detectó alto volumen de dinero + caída de cuota en esta selección en 10 minutos.'),
  'Canli mac bulunamadi':('No live match found','Kein Live-Spiel gefunden','Aucun match en direct trouvé','Geen live wedstrijd gevonden','Nessuna partita live trovata','No se encontró partido en vivo'),
  'Canlı Maçlar ':       ('Live Matches ','Live-Spiele ','Matchs en direct ','Live wedstrijden ','Partite live ','Partidos en vivo '),
  ' Canli maclar yukleniyor...':(' Loading live matches...',' Live-Spiele werden geladen...',' Chargement des matchs en direct...',' Live wedstrijden laden...',' Caricamento partite live...',' Cargando partidos en vivo...'),
  'Canlı periyot verileri için Pro üyelik gerektirir.':
    ('Live period data requires a Pro membership.','Live-Periodendaten erfordern eine Pro-Mitgliedschaft.','Les données de période en direct nécessitent un abonnement Pro.','Live periode data vereist een Pro-lidmaatschap.','I dati di periodo live richiedono un abbonamento Pro.','Los datos de período en vivo requieren membresía Pro.'),
  'Canlı veri bulunamadı':('No live data found','Keine Live-Daten gefunden','Aucune donnée en direct trouvée','Geen live gegevens gevonden','Nessun dato live trovato','No se encontraron datos en vivo'),
  ' Canlı veriler için ':(' For live data ',' Für Live-Daten ',' Pour les données en direct ',' Voor live gegevens ',' Per i dati live ',' Para datos en vivo '),
  'Çok güçlü düşüş (20%+)':('Very strong drop (20%+)','Sehr starker Abfall (20%+)','Très forte baisse (20%+)','Zeer sterke daling (20%+)','Calo molto forte (20%+)','Caída muy fuerte (20%+)'),
  ' daha fazla alarm...':(' more alarms...',' weitere Alarme...',' alarmes supplémentaires...',' meer alarmen...',' altri allarmi...',' más alarmas...'),
  '%değişimi':           ('% change','% Änderung','% changement','% verandering','% variazione','% cambio'),
  'dk once':             ('min ago','Min. her','min auparavant','min geleden','min fa','min atrás'),
  'Dropping admin veri hatası:':('Dropping admin data error:','Dropping-Admin-Datenfehler:','Erreur de données admin Dropping :','Dropping admin gegevensfout:','Errore dati admin Dropping:','Error de datos admin Dropping:'),
  ' dropping alarm bulundu!':(' dropping alarms found!',' Dropping-Alarme gefunden!',' alarmes de baisse trouvées !',' dropping-alarmen gevonden!',' allarmi di calo trovati!',' alarmas de caída encontradas!'),
  '📉 Dropping Alarm - Max Oran Eşiği':('📉 Dropping Alarm - Max Odds Threshold','📉 Dropping-Alarm - Max. Quotenschwelle','📉 Alarme de baisse - Seuil de cote max','📉 Dropping-alarm - Max odds-drempel','📉 Allarme di calo - Soglia max quote','📉 Alarma de caída - Umbral máximo de cuota'),
  'Dropping alarmları hesaplanıyor...':('Calculating dropping alarms...','Dropping-Alarme werden berechnet...','Calcul des alarmes de baisse...','Dropping-alarmen worden berekend...','Calcolo allarmi di calo...','Calculando alarmas de caída...'),
  'Dropping alarmları silindi':('Dropping alarms cleared','Dropping-Alarme gelöscht','Alarmes de baisse effacées','Dropping-alarmen gewist','Allarmi di calo cancellati','Alarmas de caída eliminadas'),
  'Dropping ayarları kaydedildi':('Dropping settings saved','Dropping-Einstellungen gespeichert','Paramètres de baisse enregistrés','Dropping-instellingen opgeslagen','Impostazioni dropping salvate','Ajustes de caída guardados'),
  'Düşüş %':              ('Drop %','Abfall %','Baisse %','Daling %','Calo %','Caída %'),
  'Düşüş (':              ('Drop (','Abfall (','Baisse (','Daling (','Calo (','Caída ('),
  '📊 Düşüş Yüzde Eşikleri':('📊 Drop Percentage Thresholds','📊 Abfall-Prozentschwellen','📊 Seuils de pourcentage de baisse','📊 Drempels voor dalingspercentage','📊 Soglie percentuali di calo','📊 Umbrales de porcentaje de caída'),
  'Eski Lider':           ('Previous Leader','Vorheriger Leader','Ancien leader','Vorige leider','Leader precedente','Líder anterior'),
  'g once':               ('d ago','T her','j auparavant','d geleden','g fa','d atrás'),
  'Gelen para':           ('Incoming money','Eingehendes Geld','Argent entrant','Inkomend geld','Denaro in arrivo','Dinero entrante'),
  'gelen para':           ('incoming money','eingehendes Geld','argent entrant','inkomend geld','denaro in arrivo','dinero entrante'),
  'Güçlü düşüş (13-20%)': ('Strong drop (13-20%)','Starker Abfall (13-20%)','Forte baisse (13-20%)','Sterke daling (13-20%)','Calo forte (13-20%)','Caída fuerte (13-20%)'),
  'Hacim':                ('Volume','Volumen','Volume','Volume','Volume','Volumen'),
  '⚡ Hacim Lideri Değişti - Ayarlar':('⚡ Volume Leader Changed - Settings','⚡ Volumen-Leader geändert - Einstellungen','⚡ Leader du volume changé - Paramètres','⚡ Volumeleider gewijzigd - Instellingen','⚡ Leader del volume cambiato - Impostazioni','⚡ Líder de volumen cambiado - Ajustes'),
  'Hacim Puan':           ('Volume Score','Volumenpunkte','Score de volume','Volume score','Punteggio volume','Puntuación de volumen'),
  'hacim şoku':           ('volume shock','Volumenschock','choc de volume','volume shock','shock di volume','choque de volumen'),
  'HACIM SOKU':           ('VOLUME SHOCK','VOLUMENSCHOCK','CHOC DE VOLUME','VOLUME SHOCK','SHOCK DI VOLUME','CHOQUE DE VOLUMEN'),
  'Henüz alarm yok.':     ('No alarms yet.','Noch keine Alarme.','Aucune alarme pour le moment.','Nog geen alarmen.','Ancora nessun allarme.','Aún no hay alarmas.'),
  'Henüz alarm yok. "Hesapla" butonuna tıklayın.':('No alarms yet. Click the "Calculate" button.','Noch keine Alarme. Klicken Sie auf die Schaltfläche "Berechnen".','Aucune alarme pour le moment. Cliquez sur le bouton "Calculer".','Nog geen alarmen. Klik op de knop "Bereken".','Ancora nessun allarme. Clicca sul pulsante "Calcola".','Aún no hay alarmas. Haz clic en el botón "Calcular".'),
  'Henüz MIM alarmı yok.':('No MIM alarms yet.','Noch keine MIM-Alarme.','Aucune alarme MIM pour le moment.','Nog geen MIM-alarmen.','Ancora nessun allarme MIM.','Aún no hay alarmas MIM.'),
  'Henuz periyot verisi yok':('No period data yet','Noch keine Periodendaten','Aucune donnée de période pour le moment','Nog geen periode data','Ancora nessun dato di periodo','Aún no hay datos de período'),
  'Hesaplama başlatılıyor...':('Calculation starting...','Berechnung wird gestartet...','Démarrage du calcul...','Berekening start...','Avvio calcolo...','Iniciando cálculo...'),
  'Hesaplama hatası':     ('Calculation error','Berechnungsfehler','Erreur de calcul','Berekeningsfout','Errore di calcolo','Error de cálculo'),
  'Kaydetme hatası':      ('Save error','Speicherfehler','Erreur d\'enregistrement','Opslagfout','Errore di salvataggio','Error al guardar'),
  'KG Hayır':             ('BTTS No','BTTS Nein','BTTS Non','BTTS Nee','GG/NG No','BTTS No'),
  ' kişi':                (' people',' Personen',' personnes',' personen',' persone',' personas'),
  'L3 ve üzeri düşüşler': ('L3 and higher drops','L3 und höhere Abfälle','Baisses L3 et plus','L3 en hogere dalingen','Cali L3 e superiori','Caídas L3 y superiores'),
  'LIDER DEGISTI':        ('LEADER CHANGED','LEADER GEÄNDERT','LEADER CHANGÉ','LEIDER GEWIJZIGD','LEADER CAMBIATO','LÍDER CAMBIADO'),
  'Lider Eşiği (%)':      ('Leader Threshold (%)','Leader-Schwelle (%)','Seuil de leader (%)','Leiderdrempel (%)','Soglia leader (%)','Umbral de líder (%)'),
  'Lig: ':                ('League: ','Liga: ','Ligue : ','Competitie: ','Lega: ','Liga: '),
  'Lisans aktif! Kalan gun: ':('License active! Days remaining: ','Lizenz aktiv! Verbleibende Tage: ','Licence active ! Jours restants : ','Licentie actief! Resterende dagen: ','Licenza attiva! Giorni rimanenti: ','¡Licencia activa! Días restantes: '),
  ' Maç':                 (' Match',' Spiel',' Match',' Wedstrijd',' Partita',' Partido'),
  'Mac: ':                ('Match: ','Spiel: ','Match : ','Wedstrijd: ','Partita: ','Partido: '),
  'Mac ID: ':             ('Match ID: ','Spiel-ID: ','ID du match : ','Wedstrijd-ID: ','ID partita: ','ID del partido: '),
  ' maç kaydedildi':      (' matches saved',' Spiele gespeichert',' matchs enregistrés',' wedstrijden opgeslagen',' partite salvate',' partidos guardados'),
  'Mac Tarihi: ':         ('Match Date: ','Spielmeldung: ','Date du match : ','Wedstrijddatum: ','Data partita: ','Fecha del partido: '),
  'Maça ':                ('Match ','Spiel ','Match ','Wedstrijd ','Partita ','Partido '),
  'Market lideri değişti. Bu seçenekte hacim üstünlüğü ele geçirildi.':
    ('Market leader changed. This selection has gained the volume advantage.',
     'Marktführer geändert. Diese Auswahl hat den Volumenvorteil übernommen.',
     'Le leader du marché a changé. Cette sélection a pris l\'avantage en volume.',
     'Marktleider veranderd. Deze selectie heeft het volumevoordeel overgenomen.',
     'Leader di mercato cambiato. Questa selezione ha conquistato il vantaggio di volume.',
     'Cambió el líder del mercado. Esta selección ha tomado la ventaja de volumen.'),
  'Max Oran 1X2':         ('Max Odds 1X2','Max Quote 1X2','Cote max 1X2','Max odds 1X2','Quota max 1X2','Cuota máx 1X2'),
  'Max Oran BTTS':        ('Max Odds BTTS','Max Quote BTTS','Cote max BTTS','Max odds BTTS','Quota max BTTS','Cuota máx BTTS'),
  'Max Oran O/U 2.5':     ('Max Odds O/U 2.5','Max Quote O/U 2.5','Cote max P/M 2.5','Max odds O/U 2.5','Quota max O/U 2.5','Cuota máx M/M 2.5'),
  'MIM admin veri hatası:':('MIM admin data error:','MIM-Admin-Datenfehler:','Erreur de données admin MIM :','MIM admin gegevensfout:','Errore dati admin MIM:','Error de datos admin MIM:'),
}

# Append more entries (continued in module variable to avoid huge dict literal)
T.update({
  'MIM ALARM HESAPLAMA':  ('MIM ALARM CALCULATION','MIM-ALARMBERECHNUNG','CALCUL D\'ALARME MIM','MIM ALARMBEREKENING','CALCOLO ALLARME MIM','CÁLCULO DE ALARMA MIM'),
  ' MIM alarm bulundu!':  (' MIM alarms found!',' MIM-Alarme gefunden!',' alarmes MIM trouvées !',' MIM-alarmen gevonden!',' allarmi MIM trovati!',' alarmas MIM encontradas!'),
  'MIM alarmları hesaplanıyor...':('Calculating MIM alarms...','MIM-Alarme werden berechnet...','Calcul des alarmes MIM...','MIM-alarmen worden berekend...','Calcolo allarmi MIM...','Calculando alarmas MIM...'),
  'MIM alarmları silindi':('MIM alarms cleared','MIM-Alarme gelöscht','Alarmes MIM effacées','MIM-alarmen gewist','Allarmi MIM cancellati','Alarmas MIM eliminadas'),
  'Min Sharp Skoru':      ('Min Sharp Score','Min. Sharp-Punktzahl','Score Sharp min','Min Sharp Score','Punteggio Sharp min','Puntuación Sharp mín'),
  'Moneyway 1X2':         ('Moneyway 1X2','Moneyway 1X2','Moneyway 1X2','Moneyway 1X2','Moneyway 1X2','Moneyway 1X2'),
  'Moneyway A/Ü 2.5':     ('Moneyway O/U 2.5','Moneyway Ü/U 2.5','Moneyway P/M 2.5','Moneyway O/U 2.5','Moneyway O/U 2.5','Moneyway M/M 2.5'),
  'Moneyway KG':          ('Moneyway BTTS','Moneyway BTTS','Moneyway BTTS','Moneyway BTTS','Moneyway GG/NG','Moneyway BTTS'),
  'OLD':                  ('OLD','ALT','ANCIEN','OUD','VECCHIO','ANTERIOR'),
  'Olası alarm hareketi yok':('No potential alarm activity','Keine potenzielle Alarmaktivität','Aucune activité d\'alarme potentielle','Geen mogelijke alarmactiviteit','Nessuna attività di allarme potenziale','Sin actividad de alarma potencial'),
  'Oran Düşüşleri':       ('Odds Drops','Quotenabfälle','Baisses de cote','Quote-dalingen','Cali quote','Caídas de cuota'),
  'Oran:':                ('Odds:','Quote:','Cote :','Odds:','Quota:','Cuota:'),
  'Para':                 ('Money','Geld','Argent','Geld','Denaro','Dinero'),
  'puan':                 ('score','Punkte','score','score','punteggio','puntuación'),
  ' saat':                (' hours',' Stunden',' heures',' uur',' ore',' horas'),
  'sa once':              ('h ago','Std. her','h auparavant','u geleden','h fa','h atrás'),
  'Saat':                 ('Hour','Stunde','Heure','Uur','Ora','Hora'),
  'sn once':              ('s ago','Sek. her','s auparavant','s geleden','s fa','s atrás'),
  'şimdi':                ('now','jetzt','maintenant','nu','adesso','ahora'),
  'Sharp ayarları kaydedildi':('Sharp settings saved','Sharp-Einstellungen gespeichert','Paramètres Sharp enregistrés','Sharp-instellingen opgeslagen','Impostazioni Sharp salvate','Ajustes Sharp guardados'),
  'Sharp config kaydetme hatası':('Sharp config save error','Sharp-Konfiguration-Speicherfehler','Erreur d\'enregistrement de la config Sharp','Sharp config opslagfout','Errore salvataggio config Sharp','Error al guardar config Sharp'),
  'Sharp signals JSON yenilendi':('Sharp signals JSON refreshed','Sharp-Signale JSON aktualisiert','JSON des signaux Sharp actualisé','Sharp signalen JSON vernieuwd','JSON segnali Sharp aggiornato','JSON de señales Sharp actualizado'),
  ' snapshot) ---\n':     (' snapshots) ---\n',' Snapshots) ---\n',' instantanés) ---\n',' snapshots) ---\n',' snapshot) ---\n',' instantáneas) ---\n'),
  'Sokun şiddeti':        ('Shock intensity','Schockintensität','Intensité du choc','Schokintensiteit','Intensità dello shock','Intensidad del choque'),
  'Sonuç':                ('Result','Ergebnis','Résultat','Resultaat','Risultato','Resultado'),
  'Toplam':               ('Total','Gesamt','Total','Totaal','Totale','Total'),
  'Toplam Snapshot: ':    ('Total Snapshots: ','Gesamt-Snapshots: ','Total des instantanés : ','Totaal snapshots: ','Snapshot totali: ','Total de instantáneas: '),
  'tümü':                 ('all','alle','tous','alle','tutti','todos'),
  '  (veri yok)\n':       ('  (no data)\n','  (keine Daten)\n','  (aucune donnée)\n','  (geen gegevens)\n','  (nessun dato)\n','  (sin datos)\n'),
  'Volume Shock alarmları silindi':('Volume Shock alarms cleared','Volume Shock-Alarme gelöscht','Alarmes Volume Shock effacées','Volume Shock-alarmen gewist','Allarmi Volume Shock cancellati','Alarmas Volume Shock eliminadas'),
  'Volume Shock ayarları kaydedildi':('Volume Shock settings saved','Volume Shock-Einstellungen gespeichert','Paramètres Volume Shock enregistrés','Volume Shock-instellingen opgeslagen','Impostazioni Volume Shock salvate','Ajustes Volume Shock guardados'),
  'Volume Shock config kaydetme hatası':('Volume Shock config save error','Volume Shock-Konfiguration-Speicherfehler','Erreur d\'enregistrement de la config Volume Shock','Volume Shock config opslagfout','Errore salvataggio config Volume Shock','Error al guardar config Volume Shock'),
  'Yenileniyor...':       ('Refreshing...','Wird aktualisiert...','Actualisation...','Vernieuwen...','Aggiornamento...','Actualizando...'),
  'Yeniden Hesapla':      ('Recalculate','Neu berechnen','Recalculer','Opnieuw berekenen','Ricalcola','Recalcular'),
  'YENI LIDER':           ('NEW LEADER','NEUER LEADER','NOUVEAU LEADER','NIEUWE LEIDER','NUOVO LEADER','NUEVO LÍDER'),
  'Yeni alarm hesaplama tamamlandı.':('New alarm calculation completed.','Neue Alarmberechnung abgeschlossen.','Calcul d\'alarme terminé.','Nieuwe alarmberekening voltooid.','Calcolo nuovo allarme completato.','Cálculo de nueva alarma completado.'),
  'Yeni Lider':           ('New Leader','Neuer Leader','Nouveau leader','Nieuwe leider','Nuovo leader','Nuevo líder'),
  'Yenilendi':            ('Refreshed','Aktualisiert','Actualisé','Vernieuwd','Aggiornato','Actualizado'),
  '\nDikkat: Sayfayı kapatmadan önce ayarları kaydetmeyi unutmayın!':
    ('\nNote: Don\'t forget to save settings before closing the page!',
     '\nHinweis: Vergessen Sie nicht, die Einstellungen vor dem Schließen der Seite zu speichern!',
     '\nAttention : n\'oubliez pas d\'enregistrer les paramètres avant de fermer la page !',
     '\nLet op: vergeet niet de instellingen op te slaan voordat u de pagina sluit!',
     '\nAttenzione: non dimenticare di salvare le impostazioni prima di chiudere la pagina!',
     '\nNota: ¡no olvides guardar los ajustes antes de cerrar la página!'),
})

# More translations for landing/rehber/sta/ui keys
T.update({
  '===== SNAPSHOT VERILERI =====\n\n':('===== SNAPSHOT DATA =====\n\n','===== SNAPSHOT-DATEN =====\n\n','===== DONNÉES INSTANTANÉ =====\n\n','===== SNAPSHOT GEGEVENS =====\n\n','===== DATI SNAPSHOT =====\n\n','===== DATOS DE INSTANTÁNEA =====\n\n'),
  'Aktif Alarm (Bugün+)':('Active Alarms (Today+)','Aktive Alarme (Heute+)','Alarmes actives (Aujourd\'hui+)','Actieve alarmen (Vandaag+)','Allarmi attivi (Oggi+)','Alarmas activas (Hoy+)'),
  'Aktif Alarm İstatistikleri':('Active Alarm Statistics','Aktive Alarmstatistik','Statistiques des alarmes actives','Statistieken actieve alarmen','Statistiche allarmi attivi','Estadísticas de alarmas activas'),
  'Aktif Maç (Bugün+)':('Active Matches (Today+)','Aktive Spiele (Heute+)','Matchs actifs (Aujourd\'hui+)','Actieve wedstrijden (Vandaag+)','Partite attive (Oggi+)','Partidos activos (Hoy+)'),
  'Alarm Engine - İşlenen Sinyaller (Son 24 Saat)':('Alarm Engine - Processed Signals (Last 24 Hours)','Alarm-Engine - Verarbeitete Signale (Letzte 24 Stunden)','Moteur d\'alarme - Signaux traités (Dernières 24 heures)','Alarm Engine - Verwerkte signalen (Laatste 24 uur)','Motore Allarmi - Segnali elaborati (Ultime 24 ore)','Motor de alarmas - Señales procesadas (Últimas 24 horas)'),
  'Çalışma Aralığı':('Run Interval','Laufintervall','Intervalle d\'exécution','Run-interval','Intervallo di esecuzione','Intervalo de ejecución'),
  'İşlenme Zamanı':('Processing Time','Verarbeitungszeit','Heure de traitement','Verwerkingstijd','Tempo di elaborazione','Tiempo de procesamiento'),
  'Scraper, Alarm Engine ve veri toplama servislerinin anlık durumu':
    ('Real-time status of Scraper, Alarm Engine and data collection services',
     'Echtzeit-Status von Scraper, Alarm-Engine und Datensammlungsdiensten',
     'État en temps réel du Scraper, du moteur d\'alarme et des services de collecte de données',
     'Realtime status van Scraper, Alarm Engine en gegevensverzamelingsdiensten',
     'Stato in tempo reale di Scraper, Motore Allarmi e servizi di raccolta dati',
     'Estado en tiempo real de Scraper, motor de alarmas y servicios de recopilación de datos'),
  'Sinyal Zamanı':('Signal Time','Signalzeit','Heure du signal','Signaaltijd','Orario segnale','Hora de señal'),
  'Son 24 Saat Özeti':('Last 24 Hours Summary','Zusammenfassung der letzten 24 Stunden','Résumé des dernières 24 heures','Samenvatting laatste 24 uur','Riepilogo ultime 24 ore','Resumen de las últimas 24 horas'),
  'Son Çalışma Geçmişi':('Recent Run History','Letzter Verlauf','Historique récent des exécutions','Recente run-geschiedenis','Cronologia esecuzioni recenti','Historial de ejecuciones recientes'),
  'Son Snapshot Sayısı':('Last Snapshot Count','Anzahl der letzten Snapshots','Nombre du dernier instantané','Aantal laatste snapshots','Conteggio ultimo snapshot','Conteo del último snapshot'),
  'Toplam Çalışma':('Total Runs','Gesamtläufe','Total des exécutions','Totaal runs','Esecuzioni totali','Ejecuciones totales'),
  'Toplam İşlenen':('Total Processed','Gesamt verarbeitet','Total traité','Totaal verwerkt','Totale elaborati','Total procesado'),
  ' ANALİZ':(' ANALYSIS',' ANALYSE',' ANALYSE',' ANALYSE',' ANALISI',' ANÁLISIS'),
  'Analizci: ':('Analyst: ','Analyst: ','Analyste : ','Analist: ','Analista: ','Analista: '),
  'Bekleyen':('Pending','Ausstehend','En attente','In afwachting','In attesa','Pendiente'),
  'İade':('Refund','Rückerstattung','Remboursement','Terugbetaling','Rimborso','Reembolso'),
  'İNCELE ↗':('REVIEW ↗','PRÜFEN ↗','EXAMINER ↗','BEKIJK ↗','ESAMINA ↗','REVISAR ↗'),
  'İptal':('Cancel','Abbrechen','Annuler','Annuleren','Annulla','Cancelar'),
  'Kaybeden':('Loser','Verlierer','Perdant','Verliezer','Perdente','Perdedor'),
  'Kaybetti':('Lost','Verloren','Perdu','Verloren','Perso','Perdió'),
  'Kazanan':('Winner','Gewinner','Gagnant','Winnaar','Vincitore','Ganador'),
  'Kazandı':('Won','Gewonnen','Gagné','Gewonnen','Vinto','Ganó'),
  '% Para':('% Money','% Geld','% Argent','% Geld','% Denaro','% Dinero'),
  ' saat önce':(' hours ago',' Stunden her',' heures auparavant',' uur geleden',' ore fa',' horas atrás'),
  'Sinyal':('Signal','Signal','Signal','Signaal','Segnale','Señal'),
})

# Second batch — covers fallback entries
T.update({
  'Oran Puan':('Odds Score','Quoten-Punkte','Score de cote','Odds-score','Punteggio quota','Puntuación de cuota'),
  'Orta seviye düşüş (8-13%)':('Medium-level drop (8-13%)','Mittlerer Abfall (8-13%)','Baisse de niveau moyen (8-13%)','Gemiddelde daling (8-13%)','Calo di livello medio (8-13%)','Caída de nivel medio (8-13%)'),
  '\n                £ Para\n            ':('\n                £ Money\n            ','\n                £ Geld\n            ','\n                £ Argent\n            ','\n                £ Geld\n            ','\n                £ Denaro\n            ','\n                £ Dinero\n            '),
  "Pro'ya Geç →":('Upgrade to Pro →','Auf Pro upgraden →','Passer à Pro →','Upgrade naar Pro →','Passa a Pro →','Cambiar a Pro →'),
  'public para':('public money','öffentliches Geld','argent public','publiek geld','denaro pubblico','dinero público'),
  'Public para akışı kısa sürede bu seçenekte yoğunlaştı.':
    ('Public money flow concentrated on this selection in a short time.',
     'Der öffentliche Geldfluss konzentrierte sich kurzfristig auf diese Auswahl.',
     'Le flux d\'argent public s\'est concentré sur cette sélection en peu de temps.',
     'Publieke geldstroom concentreerde zich in korte tijd op deze selectie.',
     'Il flusso di denaro pubblico si è concentrato su questa selezione in breve tempo.',
     'El flujo de dinero público se concentró en esta selección en poco tiempo.'),
  'Public yükseldi':('Public rose','Öffentlich gestiegen','Public a augmenté','Publiek gestegen','Pubblico aumentato','Público subió'),
  'Seçeneğe 10 dakika içinde büyük para girişi tespit edildi.':
    ('Large money inflow detected to this selection within 10 minutes.',
     'Großer Geldzufluss zu dieser Auswahl innerhalb von 10 Minuten festgestellt.',
     'Grand afflux d\'argent détecté sur cette sélection en 10 minutes.',
     'Grote geldinstroom gedetecteerd op deze selectie binnen 10 minuten.',
     'Rilevato grande afflusso di denaro su questa selezione entro 10 minuti.',
     'Se detectó gran entrada de dinero a esta selección en 10 minutos.'),
  'Seçenek: £':('Selection: £','Auswahl: £','Sélection : £','Selectie: £','Selezione: £','Selección: £'),
  'Seçim':('Selection','Auswahl','Sélection','Selectie','Selezione','Selección'),
  'Silme hatası':('Delete error','Löschfehler','Erreur de suppression','Verwijderfout','Errore di eliminazione','Error al eliminar'),
  ' kat yüksek para akışı tespit edildi.':(' times higher money flow detected.',' mal höherer Geldfluss festgestellt.',' fois plus de flux d\'argent détecté.',' keer hogere geldstroom gedetecteerd.',' volte più alto flusso di denaro rilevato.',' veces mayor flujo de dinero detectado.'),
  'Son 10 giriş ortalamasına göre X':('X times the average of last 10 entries','X-fache des Durchschnitts der letzten 10 Einträge','X fois la moyenne des 10 dernières entrées','X keer het gemiddelde van laatste 10 inzendingen','X volte la media delle ultime 10 voci','X veces el promedio de las últimas 10 entradas'),
  'Son güncelleme:':('Last update:','Letzte Aktualisierung:','Dernière mise à jour :','Laatste update:','Ultimo aggiornamento:','Última actualización:'),
  'Sonrası:':('After:','Nachher:','Après :','Na:','Dopo:','Después:'),
  'Sonrası: £':('After: £','Nachher: £','Après : £','Na: £','Dopo: £','Después: £'),
  ' — Sonrası: £':(' — After: £',' — Nachher: £',' — Après : £',' — Na: £',' — Dopo: £',' — Después: £'),
  'Su an canli mac bulunamadi':('No live match found right now','Derzeit kein Live-Spiel gefunden','Aucun match en direct trouvé pour le moment','Op dit moment geen live wedstrijd gevonden','Nessuna partita live trovata in questo momento','No se encontró partido en vivo en este momento'),
  'Şu an canlı maç bulunamadı':('No live match found right now','Derzeit kein Live-Spiel gefunden','Aucun match en direct trouvé pour le moment','Op dit moment geen live wedstrijd gevonden','Nessuna partita live trovata in questo momento','No se encontró partido en vivo en este momento'),
  'takip ediyor':('following','folgt','suit','volgt','sta seguendo','siguiendo'),
  'Tek bir seçeneğe gelen ani paranın, ilgili marketin toplam hacmine oranla yarattığı etkiyi gösterir.':
    ('Shows the impact of sudden money on a single selection relative to the total volume of that market.',
     'Zeigt die Auswirkung plötzlichen Geldes auf eine einzelne Auswahl relativ zum Gesamtvolumen dieses Marktes.',
     'Affiche l\'impact d\'un afflux soudain d\'argent sur une seule sélection par rapport au volume total de ce marché.',
     'Toont de impact van plotseling geld op één selectie ten opzichte van het totale volume van die markt.',
     'Mostra l\'impatto del denaro improvviso su una singola selezione rispetto al volume totale di quel mercato.',
     'Muestra el impacto del dinero repentino en una sola selección en relación con el volumen total de ese mercado.'),
  'Toplam: £':('Total: £','Gesamt: £','Total : £','Totaal: £','Totale: £','Total: £'),
  'Toplam Hacim':('Total Volume','Gesamtvolumen','Volume total','Totaal volume','Volume totale','Volumen total'),
  'Toplam Hacim: £':('Total Volume: £','Gesamtvolumen: £','Volume total : £','Totaal volume: £','Volume totale: £','Volumen total: £'),
  'Tüm Dropping alarmlarını silmek istediğinize emin misiniz?':('Are you sure you want to delete all Dropping alarms?','Sind Sie sicher, dass Sie alle Dropping-Alarme löschen möchten?','Êtes-vous sûr de vouloir supprimer toutes les alarmes Dropping ?','Weet u zeker dat u alle Dropping-alarmen wilt verwijderen?','Sei sicuro di voler eliminare tutti gli allarmi Dropping?','¿Está seguro de que desea eliminar todas las alarmas Dropping?'),
  'Tüm Hacim Lideri alarmlarını silmek istediğinize emin misiniz?':('Are you sure you want to delete all Volume Leader alarms?','Sind Sie sicher, dass Sie alle Volumen-Leader-Alarme löschen möchten?','Êtes-vous sûr de vouloir supprimer toutes les alarmes Volume Leader ?','Weet u zeker dat u alle Volume Leader-alarmen wilt verwijderen?','Sei sicuro di voler eliminare tutti gli allarmi Volume Leader?','¿Está seguro de que desea eliminar todas las alarmas Volume Leader?'),
  'Tüm MIM alarmlarını silmek istediğinize emin misiniz?':('Are you sure you want to delete all MIM alarms?','Sind Sie sicher, dass Sie alle MIM-Alarme löschen möchten?','Êtes-vous sûr de vouloir supprimer toutes les alarmes MIM ?','Weet u zeker dat u alle MIM-alarmen wilt verwijderen?','Sei sicuro di voler eliminare tutti gli allarmi MIM?','¿Está seguro de que desea eliminar todas las alarmas MIM?'),
  'Tumu':('All','Alle','Tous','Alle','Tutti','Todos'),
  'Ü/A 2.5':('U/O 2.5','U/Ü 2.5','M/P 2.5','U/O 2.5','U/O 2.5','M/M 2.5'),
  'Üst ':('Over ','Über ','Plus ','Over ','Over ','Más '),
  'Üst 2.5':('Over 2.5','Über 2.5','Plus 2.5','Over 2.5','Over 2.5','Más 2.5'),
  ' ÜST':(' OVER',' ÜBER',' PLUS',' OVER',' OVER',' MÁS'),
  ' üyelik gerekmektedir':(' membership is required',' Mitgliedschaft erforderlich',' adhésion requise',' lidmaatschap vereist',' è richiesto l\'abbonamento',' se requiere membresía'),
  'Veri yüklenirken hata oluştu.':('An error occurred while loading data.','Beim Laden der Daten ist ein Fehler aufgetreten.','Une erreur s\'est produite lors du chargement des données.','Er is een fout opgetreden bij het laden van gegevens.','Si è verificato un errore durante il caricamento dei dati.','Ocurrió un error al cargar los datos.'),
  'Volume Leader admin veri hatası:':('Volume Leader admin data error:','Volume Leader-Admin-Datenfehler:','Erreur de données admin Volume Leader :','Volume Leader admin gegevensfout:','Errore dati admin Volume Leader:','Error de datos admin Volume Leader:'),
  ' yeni alarm bulundu!':(' new alarms found!',' neue Alarme gefunden!',' nouvelles alarmes trouvées !',' nieuwe alarmen gevonden!',' nuovi allarmi trovati!',' nuevas alarmas encontradas!'),
  'yeni para':('new money','neues Geld','nouvel argent','nieuw geld','nuovo denaro','dinero nuevo'),
  '\n                    Yükleniyor...\n                ':('\n                    Loading...\n                ','\n                    Wird geladen...\n                ','\n                    Chargement...\n                ','\n                    Laden...\n                ','\n                    Caricamento...\n                ','\n                    Cargando...\n                '),
  'YÜZDE':('PERCENTAGE','PROZENTSATZ','POURCENTAGE','PERCENTAGE','PERCENTUALE','PORCENTAJE'),
  '\n                % Yüzde\n            ':('\n                % Percentage\n            ','\n                % Prozentsatz\n            ','\n                % Pourcentage\n            ','\n                % Percentage\n            ','\n                % Percentuale\n            ','\n                % Porcentaje\n            '),
  'Mar':('Mar','Mär','Mar','Mrt','Mar','Mar'),
  'May':('May','Mai','Mai','Mei','Mag','May'),
  'SmartXFlow Monitor':('SmartXFlow Monitor','SmartXFlow Monitor','SmartXFlow Monitor','SmartXFlow Monitor','SmartXFlow Monitor','SmartXFlow Monitor'),
  'Telegram':('Telegram','Telegram','Telegram','Telegram','Telegram','Telegram'),
  'Bu maç için alarm hareketi yok.':('No alarm activity for this match.','Keine Alarmaktivität für dieses Spiel.','Aucune activité d\'alarme pour ce match.','Geen alarmactiviteit voor deze wedstrijd.','Nessuna attività di allarme per questa partita.','Sin actividad de alarma para este partido.'),
  '🇫🇷 Français':('🇫🇷 French','🇫🇷 Französisch','🇫🇷 Français','🇫🇷 Frans','🇫🇷 Francese','🇫🇷 Francés'),
  '🇹🇷 Türkçe':('🇹🇷 Turkish','🇹🇷 Türkisch','🇹🇷 Turc','🇹🇷 Turks','🇹🇷 Turco','🇹🇷 Turco'),
  'Gerçek zamanlı veri, akıllı sinyaller.':('Real-time data, smart signals.','Echtzeit-Daten, intelligente Signale.','Données en temps réel, signaux intelligents.','Realtime gegevens, slimme signalen.','Dati in tempo reale, segnali intelligenti.','Datos en tiempo real, señales inteligentes.'),
  'Piyasayı Okuyan':('Reading the Market','Den Markt lesen','Lire le marché','De markt lezen','Leggere il mercato','Leer el mercado'),
  'Süper Lig':('Super League','Süper Lig','Süper Lig','Süper Lig','Süper Lig','Süper Lig'),
  'Deutsch':('German','Deutsch','Allemand','Duits','Tedesco','Alemán'),
  'English':('English','Englisch','Anglais','Engels','Inglese','Inglés'),
  'Español':('Spanish','Spanisch','Espagnol','Spaans','Spagnolo','Español'),
  'Français':('French','Französisch','Français','Frans','Francese','Francés'),
  'Italiano':('Italian','Italienisch','Italien','Italiaans','Italiano','Italiano'),
  'Nederlands':('Dutch','Niederländisch','Néerlandais','Nederlands','Olandese','Neerlandés'),
  'Türkçe':('Turkish','Türkisch','Turc','Turks','Turco','Turco'),
  'SmartXFlow':('SmartXFlow','SmartXFlow','SmartXFlow','SmartXFlow','SmartXFlow','SmartXFlow'),
  'SmartXFlow?':('SmartXFlow?','SmartXFlow?','SmartXFlow?','SmartXFlow?','SmartXFlow?','SmartXFlow?'),
  'Garanti Bankası':('Garanti Bankası','Garanti Bankası','Garanti Bankası','Garanti Bankası','Garanti Bankası','Garanti Bankası'),
  'Kerimcan Öztoprak':('Kerimcan Öztoprak','Kerimcan Öztoprak','Kerimcan Öztoprak','Kerimcan Öztoprak','Kerimcan Öztoprak','Kerimcan Öztoprak'),
  'Not: Bu özellik çok yakında eklenecektir.':('Note: This feature will be added very soon.','Hinweis: Diese Funktion wird sehr bald hinzugefügt.','Note : cette fonctionnalité sera ajoutée très bientôt.','Opmerking: deze functie wordt zeer binnenkort toegevoegd.','Nota: questa funzionalità sarà aggiunta molto presto.','Nota: esta función se añadirá muy pronto.'),
  'analiz aracıdır':('is an analysis tool','ist ein Analysewerkzeug','est un outil d\'analyse','is een analyse-tool','è uno strumento di analisi','es una herramienta de análisis'),
  'gerçek piyasa verileriyle':('with real market data','mit echten Marktdaten','avec des données de marché réelles','met echte marktgegevens','con dati di mercato reali','con datos reales del mercado'),
  'alarm bandında':('in the alarm band','im Alarmband','dans la bande d\'alarmes','in de alarmband','nella banda allarmi','en la banda de alarmas'),
  'Alarm türleri:':('Alarm types:','Alarmtypen:','Types d\'alarme :','Alarmtypen:','Tipi di allarme:','Tipos de alarma:'),
  'Anlık skor ve dakika bilgisi:':('Live score and minute info:','Live-Spielstand und Minuten-Info:','Score en direct et info minute :','Live score en minuut info:','Punteggio live e info minuti:','Marcador en vivo e información de minutos:'),
  '"Canlı"':('"Live"','"Live"','"En direct"','"Live"','"Live"','"En vivo"'),
  'Canlı maç alarmı:':('Live match alarm:','Live-Spiel-Alarm:','Alarme de match en direct :','Live wedstrijd alarm:','Allarme partita live:','Alarma de partido en vivo:'),
  'Canlı oran değişimleri:':('Live odds changes:','Live-Quotenänderungen:','Changements de cotes en direct :','Live odds-veranderingen:','Cambi quote live:','Cambios de cuotas en vivo:'),
  'Canlı oran takibi neden önemli, oran alarmı nasıl çalışır, oranı düşen maçlar ne anlama gelir? Maç içi sinyalleri daha doğru okuyun.':
    ('Why is live odds tracking important, how do odds alarms work, what do matches with falling odds mean? Understand in-match signals more deeply.',
     'Warum ist Live-Quotenverfolgung wichtig, wie funktionieren Quotenalarme, was bedeuten Spiele mit fallenden Quoten? Verstehen Sie In-Match-Signale tiefer.',
     'Pourquoi le suivi des cotes en direct est-il important, comment fonctionnent les alarmes de cote, que signifient les matchs aux cotes en baisse ? Comprenez plus en profondeur les signaux en match.',
     'Waarom is live odds-tracking belangrijk, hoe werken odds-alarmen, wat betekenen wedstrijden met dalende odds? Begrijp in-match signalen dieper.',
     'Perché è importante il tracciamento delle quote live, come funzionano gli allarmi quote, cosa significano le partite con quote in calo? Comprendi più a fondo i segnali in partita.',
     '¿Por qué es importante el seguimiento de cuotas en vivo, cómo funcionan las alarmas de cuotas, qué significan los partidos con cuotas en caída? Comprende mejor las señales en partido.'),
  'canlı oran takibi, oran alarmı, oranı düşen maçlar, canlı maç takibi, oran sinyali, alarm sistemi, SmartXFlow':
    ('live odds tracking, odds alarm, matches with falling odds, live match tracking, odds signal, alarm system, SmartXFlow',
     'Live-Quotenverfolgung, Quotenalarm, Spiele mit fallenden Quoten, Live-Spielverfolgung, Quotensignal, Alarmsystem, SmartXFlow',
     'suivi des cotes en direct, alarme de cote, matchs aux cotes en baisse, suivi de match en direct, signal de cote, système d\'alarme, SmartXFlow',
     'live odds tracking, odds alarm, wedstrijden met dalende odds, live wedstrijd tracking, odds signaal, alarmsysteem, SmartXFlow',
     'tracciamento quote live, allarme quote, partite con quote in calo, tracciamento partita live, segnale quote, sistema di allarme, SmartXFlow',
     'seguimiento de cuotas en vivo, alarma de cuotas, partidos con cuotas en caída, seguimiento de partido en vivo, señal de cuotas, sistema de alarmas, SmartXFlow'),
  'Canlı Oran Takibi ve Oran Alarmı Rehberi | SmartXFlow':
    ('Live Odds Tracking and Odds Alarm Guide | SmartXFlow',
     'Leitfaden für Live-Quotenverfolgung und Quotenalarm | SmartXFlow',
     'Guide de suivi des cotes en direct et d\'alarme de cote | SmartXFlow',
     'Live odds tracking en odds-alarm gids | SmartXFlow',
     'Guida al tracciamento quote live e allarmi quote | SmartXFlow',
     'Guía de seguimiento de cuotas en vivo y alarma de cuotas | SmartXFlow'),
  'Canlı sekmede göreceğiniz veriler:':('Data you\'ll see in the Live tab:','Daten, die Sie im Live-Tab sehen:','Données que vous verrez dans l\'onglet En direct :','Gegevens die u in het Live-tabblad ziet:','Dati che vedrai nel tab Live:','Datos que verás en la pestaña En vivo:'),
  'Maç içi para akışı:':('In-match money flow:','Geldfluss im Spiel:','Flux d\'argent pendant le match :','Geldstroom in wedstrijd:','Flusso di denaro in partita:','Flujo de dinero en partido:'),
  'Dropping Odds':('Dropping Odds','Dropping Odds','Cotes en baisse','Dropping Odds','Quote in calo','Cuotas en caída'),
  'Moneyway':('Moneyway','Moneyway','Moneyway','Moneyway','Moneyway','Moneyway'),
  ' Nedir?':(' What is it?',' Was ist das?',' Qu\'est-ce que c\'est ?',' Wat is het?',' Cos\'è?',' ¿Qué es?'),
  'Sharp · Big Money · Dropping…':('Sharp · Big Money · Dropping…','Sharp · Big Money · Dropping…','Sharp · Big Money · Dropping…','Sharp · Big Money · Dropping…','Sharp · Big Money · Dropping…','Sharp · Big Money · Dropping…'),
  'MIM':('MIM','MIM','MIM','MIM','MIM','MIM'),
})


# Final batch — remaining real-Turkish entries
T.update({
  'Admin Panel':('Admin Panel','Admin-Panel','Panneau d\'administration','Beheerderspaneel','Pannello di amministrazione','Panel de administración'),
  '\n                    MIM alarmı, piyasa etkisini ölçer. Impact değeri ne kadar yüksekse, o seçim için para akışı o kadar güçlüdür.\n                ':
    ('\n                    The MIM alarm measures market impact. The higher the impact value, the greater the effect of the money.\n                ',
     '\n                    Der MIM-Alarm misst die Marktauswirkung. Je höher der Impact-Wert, desto größer die Wirkung des Geldes.\n                ',
     '\n                    L\'alarme MIM mesure l\'impact sur le marché. Plus la valeur d\'impact est élevée, plus l\'effet de l\'argent est grand.\n                ',
     '\n                    Het MIM-alarm meet de marktimpact. Hoe hoger de impactwaarde, hoe groter het effect van het geld.\n                ',
     '\n                    L\'allarme MIM misura l\'impatto sul mercato. Più alto è il valore di impatto, maggiore è l\'effetto del denaro.\n                ',
     '\n                    La alarma MIM mide el impacto en el mercado. Cuanto mayor sea el valor de impacto, mayor será el efecto del dinero.\n                '),
  'MIM ayarları kaydedildi':('MIM settings saved','MIM-Einstellungen gespeichert','Paramètres MIM enregistrés','MIM-instellingen opgeslagen','Impostazioni MIM salvate','Ajustes MIM guardados'),
  'Min. Hacim (£)':('Min. Volume (£)','Min. Volumen (£)','Volume min (£)','Min. volume (£)','Volume min (£)','Volumen mín. (£)'),
  'Min. Hacim 1X2 (£)':('Min. Volume 1X2 (£)','Min. Volumen 1X2 (£)','Volume min 1X2 (£)','Min. volume 1X2 (£)','Volume min 1X2 (£)','Volumen mín. 1X2 (£)'),
  'Min. Hacim BTTS (£)':('Min. Volume BTTS (£)','Min. Volumen BTTS (£)','Volume min BTTS (£)','Min. volume BTTS (£)','Volume min BTTS (£)','Volumen mín. BTTS (£)'),
  'Min. Hacim O/U (£)':('Min. Volume O/U (£)','Min. Volumen O/U (£)','Volume min O/U (£)','Min. volume O/U (£)','Volume min O/U (£)','Volumen mín. O/U (£)'),
  'Min. Impact Eşiği':('Min. Impact Threshold','Min. Impact-Schwelle','Seuil d\'impact min','Min. impact-drempel','Soglia impatto min','Umbral mínimo de impacto'),
  'Minimum impact değeri (varsayılan: 0.10)':('Minimum impact value (default: 0.10)','Minimaler Impact-Wert (Standard: 0.10)','Valeur d\'impact minimale (défaut : 0,10)','Minimale impactwaarde (standaard: 0.10)','Valore di impatto minimo (predefinito: 0,10)','Valor de impacto mínimo (por defecto: 0,10)'),
  'Minimum pay oranı (varsayılan: %50)':('Minimum share ratio (default: 50%)','Minimaler Anteil (Standard: 50%)','Ratio minimum de part (défaut : 50 %)','Minimale aandeelverhouding (standaard: 50%)','Quota minima (predefinito: 50%)','Proporción mínima (por defecto: 50%)'),
  'Minimum toplam hacim':('Minimum total volume','Minimales Gesamtvolumen','Volume total minimum','Minimaal totaal volume','Volume totale minimo','Volumen total mínimo'),
  'Moneyway Alt/Üst 2.5':('Moneyway Over/Under 2.5','Moneyway Über/Unter 2.5','Moneyway Plus/Moins 2.5','Moneyway Over/Under 2.5','Moneyway Over/Under 2.5','Moneyway Más/Menos 2.5'),
  'Olay sonrası: £':('After event: £','Nach Ereignis: £','Après l\'événement : £','Na gebeurtenis: £','Dopo evento: £','Después del evento: £'),
  'ORAN':('ODDS','QUOTE','COTE','ODDS','QUOTE','CUOTA'),
  'Oran A/Ü 2.5':('Odds O/U 2.5','Quote Ü/U 2.5','Cote P/M 2.5','Odds O/U 2.5','Quota O/U 2.5','Cuota M/M 2.5'),
  'Oran: ':('Odds: ','Quote: ','Cote : ','Odds: ','Quota: ','Cuota: '),
  'Oran açılıştan itibaren ciddi şekilde düştü.':('Odds dropped significantly since opening.','Quoten sind seit der Eröffnung deutlich gefallen.','La cote a fortement baissé depuis l\'ouverture.','Odds zijn sinds opening sterk gedaald.','Le quote sono calate notevolmente dall\'apertura.','Las cuotas han caído significativamente desde la apertura.'),
  'Oran değişim':('Odds change','Quotenänderung','Changement de cote','Odds-verandering','Variazione quota','Cambio de cuota'),
  'SmartXFlow {{ title }}. Platform kullanım koşulları ve yasal bilgiler.':
    ('SmartXFlow {{ title }}. Platform terms of use and legal information.',
     'SmartXFlow {{ title }}. Plattform-Nutzungsbedingungen und rechtliche Informationen.',
     'SmartXFlow {{ title }}. Conditions d\'utilisation de la plateforme et informations légales.',
     'SmartXFlow {{ title }}. Gebruiksvoorwaarden van het platform en juridische informatie.',
     'SmartXFlow {{ title }}. Termini di utilizzo della piattaforma e informazioni legali.',
     'SmartXFlow {{ title }}. Términos de uso de la plataforma e información legal.'),
  'SmartXFlow nedir, oran hareketi analiz, para akışı takip, bahis piyasa analizi, dropping odds nedir, moneyway nedir':
    ('What is SmartXFlow, odds movement analysis, money flow tracking, betting market analysis, what are dropping odds, what is moneyway',
     'Was ist SmartXFlow, Quotenbewegungsanalyse, Geldfluss-Tracking, Wettmarktanalyse, was sind fallende Quoten, was ist Moneyway',
     'Qu\'est-ce que SmartXFlow, analyse du mouvement des cotes, suivi des flux d\'argent, analyse du marché des paris, qu\'est-ce que les cotes en baisse, qu\'est-ce que moneyway',
     'Wat is SmartXFlow, odds-bewegingsanalyse, geldstroom-tracking, wedmarktanalyse, wat zijn dropping odds, wat is moneyway',
     'Cos\'è SmartXFlow, analisi del movimento delle quote, tracciamento dei flussi di denaro, analisi del mercato delle scommesse, cosa sono le quote in calo, cos\'è moneyway',
     'Qué es SmartXFlow, análisis de movimiento de cuotas, seguimiento de flujos de dinero, análisis del mercado de apuestas, qué son las cuotas en caída, qué es moneyway'),
  'SmartXFlow fiyat, oran takip paketi, bahis analiz üyelik, para akışı takip, canlı oran takip planı':
    ('SmartXFlow pricing, odds tracking package, betting analysis membership, money flow tracking, live odds tracking plan',
     'SmartXFlow Preise, Quotenverfolgungspaket, Wettanalyse-Mitgliedschaft, Geldfluss-Tracking, Live-Quotenverfolgungsplan',
     'Tarifs SmartXFlow, forfait de suivi des cotes, abonnement d\'analyse de paris, suivi des flux d\'argent, plan de suivi des cotes en direct',
     'SmartXFlow prijzen, odds-trackingpakket, wedanalyse-lidmaatschap, geldstroom-tracking, live odds-trackingplan',
     'Prezzi SmartXFlow, pacchetto di tracciamento quote, abbonamento di analisi scommesse, tracciamento flussi di denaro, piano di tracciamento quote live',
     'Precios SmartXFlow, paquete de seguimiento de cuotas, membresía de análisis de apuestas, seguimiento de flujos de dinero, plan de seguimiento de cuotas en vivo'),
  'oran takibi, para akışı, bahis analiz, odds movement, dropping odds, akıllı para, moneyway, canlı oran, piyasa analizi, ':
    ('odds tracking, money flow, betting analysis, odds movement, dropping odds, smart money, moneyway, live odds, market analysis, ',
     'Quotenverfolgung, Geldfluss, Wettanalyse, Quotenbewegung, fallende Quoten, intelligentes Geld, Moneyway, Live-Quoten, Marktanalyse, ',
     'suivi des cotes, flux d\'argent, analyse de paris, mouvement des cotes, cotes en baisse, argent intelligent, moneyway, cotes en direct, analyse de marché, ',
     'odds-tracking, geldstroom, wedanalyse, odds-beweging, dropping odds, slim geld, moneyway, live odds, marktanalyse, ',
     'tracciamento quote, flusso di denaro, analisi scommesse, movimento quote, quote in calo, denaro intelligente, moneyway, quote live, analisi di mercato, ',
     'seguimiento de cuotas, flujo de dinero, análisis de apuestas, movimiento de cuotas, cuotas en caída, dinero inteligente, moneyway, cuotas en vivo, análisis de mercado, '),
})


# Long-form rehber translations
T.update({
  'Sert oran düşüşü alarmı:':('Sharp odds drop alarm:','Sharp Quotenabfall-Alarm:','Alarme de forte baisse de cote :','Sharp odds-daling alarm:','Allarme calo netto quote:','Alarma de caída brusca de cuota:'),
  'Uyumsuzluk alarmı:':('Discrepancy alarm:','Diskrepanzalarm:','Alarme de divergence :','Discrepantie-alarm:','Allarme di discrepanza:','Alarma de discrepancia:'),
  'Yoğun para akışı alarmı:':('Heavy money flow alarm:','Hoher Geldfluss-Alarm:','Alarme de fort flux d\'argent :','Zwaar geldstroom-alarm:','Allarme di forte flusso di denaro:','Alarma de fuerte flujo de dinero:'),
  'Ani sert düşüş:':('Sudden sharp drop:','Plötzlicher starker Abfall:','Forte baisse soudaine :','Plotselinge sterke daling:','Calo improvviso netto:','Caída brusca repentina:'),
  'Çok yönlü düşüş (1X2 hepsi):':('Multi-directional drop (all 1X2):','Mehrfacher Abfall (alle 1X2):','Baisse multidirectionnelle (tous 1X2) :','Meervoudige daling (alle 1X2):','Calo multi-direzionale (tutti 1X2):','Caída multidireccional (todos 1X2):'),
  'Dropping Odds (Düşen Oranlar):':('Dropping Odds:','Fallende Quoten:','Cotes en baisse :','Dropping Odds:','Quote in calo:','Cuotas en caída:'),
  'henüz kamuoyuna yansımamış bilgileri':('information not yet public','noch nicht öffentliche Informationen','informations pas encore publiques','informatie die nog niet openbaar is','informazioni non ancora pubbliche','información aún no pública'),
  'Kademeli düşüş:':('Gradual drop:','Stufenweiser Abfall:','Baisse graduelle :','Geleidelijke daling:','Calo graduale:','Caída gradual:'),
  'oran analizi, oran değişimi, dropping odds, düşen oranlar, bahis oranı analizi, oran hareketi, SmartXFlow':
    ('odds analysis, odds change, dropping odds, falling odds, betting odds analysis, odds movement, SmartXFlow',
     'Quotenanalyse, Quotenänderung, fallende Quoten, Quotenbewegung, Wettquotenanalyse, SmartXFlow',
     'analyse des cotes, changement de cote, cotes en baisse, mouvement des cotes, analyse des cotes de paris, SmartXFlow',
     'odds analyse, odds verandering, dropping odds, dalende odds, wedquotes analyse, odds beweging, SmartXFlow',
     'analisi quote, cambio quote, quote in calo, movimento quote, analisi quote scommesse, SmartXFlow',
     'análisis de cuotas, cambio de cuotas, cuotas en caída, movimiento de cuotas, análisis de cuotas de apuestas, SmartXFlow'),
  'piyasa tabanlı analiz':('market-based analysis','marktbasierte Analyse','analyse basée sur le marché','marktgebaseerde analyse','analisi basata sul mercato','análisis basado en el mercado'),
  'Son dakika sert düşüş:':('Last-minute sharp drop:','Letzter-Minute-Abfall:','Forte baisse de dernière minute :','Laatste-minuut sterke daling:','Calo netto all\'ultimo minuto:','Caída brusca de último minuto:'),
  'zaman içinde nasıl değiştiğini':('how it changes over time','wie es sich im Laufe der Zeit ändert','comment cela évolue dans le temps','hoe het in de loop van de tijd verandert','come cambia nel tempo','cómo cambia con el tiempo'),
  'oran analizi, maç analizi, oran değişimi, para hareketi, canlı oran takibi, dropping odds, moneyway, oran alarmı, SmartXFlow rehber':
    ('odds analysis, match analysis, odds change, money flow, live odds tracking, dropping odds, moneyway, odds alarm, SmartXFlow guide',
     'Quotenanalyse, Spielanalyse, Quotenänderung, Geldfluss, Live-Quotenverfolgung, fallende Quoten, Moneyway, Quotenalarm, SmartXFlow-Handbuch',
     'analyse des cotes, analyse de match, changement de cote, flux d\'argent, suivi des cotes en direct, cotes en baisse, moneyway, alarme de cote, guide SmartXFlow',
     'odds analyse, wedstrijd analyse, odds verandering, geldstroom, live odds tracking, dropping odds, moneyway, odds alarm, SmartXFlow gids',
     'analisi quote, analisi partita, cambio quote, flusso di denaro, tracciamento quote live, quote in calo, moneyway, allarme quote, guida SmartXFlow',
     'análisis de cuotas, análisis de partido, cambio de cuotas, flujo de dinero, seguimiento de cuotas en vivo, cuotas en caída, moneyway, alarma de cuotas, guía SmartXFlow'),
  '%40-55 arası dengeli dağılım:':('Balanced 40-55% distribution:','Ausgewogene 40-55% Verteilung:','Distribution équilibrée 40-55 % :','Gebalanceerde 40-55% verdeling:','Distribuzione bilanciata 40-55%:','Distribución equilibrada 40-55%:'),
  '%55+ tek yöne yığılma:':('55%+ stacked on one side:','55%+ auf einer Seite gehäuft:','55 %+ accumulés d\'un côté :','55%+ opgestapeld aan één kant:','55%+ accumulato su un lato:','55%+ acumulado en un lado:'),
  'Ani yüzde değişimi:':('Sudden percentage change:','Plötzliche Prozentänderung:','Changement soudain de pourcentage :','Plotselinge procentuele verandering:','Variazione percentuale improvvisa:','Cambio porcentual repentino:'),
  'aynı yönde':('in the same direction','in dieselbe Richtung','dans le même sens','in dezelfde richting','nella stessa direzione','en la misma dirección'),
  'aynı yöne işaret ettiğinde':('when pointing in the same direction','wenn sie in die gleiche Richtung zeigen','lorsqu\'ils pointent dans la même direction','wanneer ze in dezelfde richting wijzen','quando puntano nella stessa direzione','cuando apuntan en la misma dirección'),
  'bahis miktarının yüzdesel dağılımını':('the percentage distribution of bet amounts','die prozentuale Verteilung der Wettbeträge','la distribution en pourcentage des montants pariés','de procentuele verdeling van inzetbedragen','la distribuzione percentuale degli importi delle scommesse','la distribución porcentual de los montos apostados'),
  'gerçek pozisyonlarını':('their actual positions','ihre tatsächlichen Positionen','leurs positions réelles','hun werkelijke posities','le loro posizioni reali','sus posiciones reales'),
  'Maçlarda para hareketi nedir, oran ve para birlikte nasıl okunur? Piyasa yönünü anlamak için bilmeniz gerekenleri öğrenin.':
    ('What is money movement in matches, how to read odds and money together? Learn what you need to know to understand market direction.',
     'Was ist Geldbewegung in Spielen, wie liest man Quoten und Geld zusammen? Erfahren Sie, was Sie wissen müssen, um die Marktrichtung zu verstehen.',
     'Qu\'est-ce que le mouvement de l\'argent dans les matchs, comment lire ensemble les cotes et l\'argent ? Apprenez ce que vous devez savoir pour comprendre la direction du marché.',
     'Wat is geldbeweging in wedstrijden, hoe lees je odds en geld samen? Leer wat je moet weten om de marktrichting te begrijpen.',
     'Cos\'è il movimento di denaro nelle partite, come leggere insieme quote e denaro? Scopri cosa devi sapere per capire la direzione del mercato.',
     '¿Qué es el movimiento de dinero en los partidos, cómo leer cuotas y dinero juntos? Aprende lo que necesitas saber para entender la dirección del mercado.'),
  'Moneyway verileri nasıl okunur?':('How to read Moneyway data?','Wie liest man Moneyway-Daten?','Comment lire les données Moneyway ?','Hoe lees je Moneyway-gegevens?','Come leggere i dati Moneyway?','¿Cómo leer los datos de Moneyway?'),
  'para hareketi, moneyway, para akışı, oran ve para okuma, bahis para hareketi, piyasa yönü, SmartXFlow':
    ('money movement, moneyway, money flow, reading odds and money, betting money movement, market direction, SmartXFlow',
     'Geldbewegung, Moneyway, Geldfluss, Quoten und Geld lesen, Wettgeldbewegung, Marktrichtung, SmartXFlow',
     'mouvement d\'argent, moneyway, flux d\'argent, lecture des cotes et de l\'argent, mouvement de l\'argent de pari, direction du marché, SmartXFlow',
     'geldbeweging, moneyway, geldstroom, odds en geld lezen, wedgeldbeweging, marktrichting, SmartXFlow',
     'movimento di denaro, moneyway, flusso di denaro, lettura quote e denaro, movimento denaro scommesse, direzione mercato, SmartXFlow',
     'movimiento de dinero, moneyway, flujo de dinero, lectura de cuotas y dinero, movimiento de dinero de apuestas, dirección de mercado, SmartXFlow'),
  'Para Hareketi Nedir? Moneyway Nasıl Okunur? | SmartXFlow':
    ('What is Money Movement? How to Read Moneyway? | SmartXFlow',
     'Was ist Geldbewegung? Wie liest man Moneyway? | SmartXFlow',
     'Qu\'est-ce que le mouvement d\'argent ? Comment lire Moneyway ? | SmartXFlow',
     'Wat is geldbeweging? Hoe Moneyway lezen? | SmartXFlow',
     'Cos\'è il movimento di denaro? Come leggere Moneyway? | SmartXFlow',
     '¿Qué es el movimiento de dinero? ¿Cómo leer Moneyway? | SmartXFlow'),
})


def main():
    if not os.path.exists(MASTER):
        print('master not found'); sys.exit(1)
    with open(MASTER, encoding='utf-8') as fh:
        rows = list(csv.DictReader(fh))
        fields = list(rows[0].keys()) if rows else FIELDS
    miss = []
    filled = 0
    for r in rows:
        if r.get('en','').strip(): continue
        tr = r.get('tr','')
        if tr in T:
            en, de, fr, nl, it, es = T[tr]
            r['en'], r['de'], r['fr'], r['nl'], r['it'], r['es'] = en, de, fr, nl, it, es
            filled += 1
        else:
            miss.append((r['key'], tr))
    # Fallback for missing: copy TR (better than nothing for structural / unknown)
    for r in rows:
        if not r.get('en','').strip():
            for L in LANGS:
                r[L] = r.get('tr','')
    rows.sort(key=lambda r: r['key'])
    with open(MASTER, 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=fields, quoting=csv.QUOTE_ALL)
        w.writeheader()
        for r in rows:
            w.writerow({f: r.get(f,'') for f in fields})
    print(f'filled {filled} entries from dictionary')
    print(f'fallback (tr-copy) for {len(miss)} entries')
    if miss and '--show-miss' in sys.argv:
        for k, t in miss[:50]: print(' ',k,'|',repr(t)[:80])


if __name__ == '__main__':
    main()
