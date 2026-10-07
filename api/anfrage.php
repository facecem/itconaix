<?php
/**
 * IT conAIX – Termin- und Kontaktanfragen
 * ---------------------------------------------------------------
 * Nimmt Anfragen aus dem Terminfenster der Website entgegen (JSON per POST),
 * prüft sie und schickt sie per E-Mail an das Team. Der Absender bekommt
 * eine automatische Eingangsbestätigung.
 *
 * Es wird nichts dauerhaft gespeichert. Für den Missbrauchsschutz liegt
 * höchstens eine Stunde lang ein gehashter Wert der IP-Adresse im
 * temporären Ordner des Servers.
 */
declare(strict_types=1);

// ---------- Einstellungen ----------
const MAIL_TO     = 'info@itconaix.de';      // hier kommen die Anfragen an
const MAIL_FROM   = 'info@itconaix.de';      // muss ein echtes Postfach der Domain sein (SPF)
const FROM_NAME   = 'IT conAIX Website';
const SITE_URL    = 'https://itconaix.de';

// Termine – müssen zum Terminfenster auf der Website passen
const SLOT_FROM   = 12 * 60;                 // 12:00
const SLOT_TO     = 19 * 60;                 // letzter Beginn 18:30
const SLOT_MIN    = 30;
const LEAD_HOURS  = 18;                      // Abstand bei der Website; hier mit etwas Toleranz geprüft
const DAYS_AHEAD  = 42;
const KINDS       = ['Videocall', 'Telefon'];
const THEMEN      = ['IT-Betreuung', 'Website oder Shop', 'Software oder App', 'Automatisierung und KI', 'Etwas anderes'];

// Missbrauchsschutz
const RATE_MAX    = 5;                       // Anfragen …
const RATE_WINDOW = 3600;                    // … pro Stunde und Absender
const MIN_FILL_MS = 800;                     // schneller ausgefüllt = sicher ein Bot (Autofill + Klick dauert länger)

date_default_timezone_set('Europe/Berlin');
header('Content-Type: application/json; charset=utf-8');
header('X-Robots-Tag: noindex');
header('Cache-Control: no-store');

const WOCHENTAGE = ['Sonntag', 'Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag'];
const MONATE     = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];

function antwort(int $code, array $daten): void
{
    http_response_code($code);
    echo json_encode($daten, JSON_UNESCAPED_UNICODE);
    exit;
}

function fehler(int $code, string $text): void
{
    antwort($code, ['ok' => false, 'error' => $text]);
}

/** Textfeld holen, Steuerzeichen entfernen, Länge begrenzen. */
function feld(array $in, string $key, int $max): string
{
    $v = (isset($in[$key]) && is_scalar($in[$key])) ? trim((string) $in[$key]) : '';
    $v = (string) preg_replace('/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/u', '', $v);
    return mb_substr($v, 0, $max, 'UTF-8');
}

/** Für Betreff und Kopfzeilen: keine Zeilenumbrüche (verhindert Header-Injection). */
function einzeilig(string $s): string
{
    return trim((string) preg_replace('/\s+/u', ' ', $s));
}

function kopf(string $s): string
{
    return '=?UTF-8?B?' . base64_encode($s) . '?=';
}

function datumLang(DateTimeImmutable $d): string
{
    return WOCHENTAGE[(int) $d->format('w')] . ', ' . $d->format('j') . '. ' . MONATE[(int) $d->format('n') - 1] . ' ' . $d->format('Y');
}

function sende(string $an, string $betreff, string $text, string $antwortAn = ''): bool
{
    $header = [
        'From: ' . kopf(FROM_NAME) . ' <' . MAIL_FROM . '>',
        'MIME-Version: 1.0',
        'Content-Type: text/plain; charset=UTF-8',
        'Content-Transfer-Encoding: 8bit',
        'X-Mailer: itconaix-website',
    ];
    if ($antwortAn !== '') {
        $header[] = 'Reply-To: ' . $antwortAn;
    }
    $header = implode("\r\n", $header);
    $betreff = kopf($betreff);
    // Absenderadresse auf Umschlagsebene setzen (wichtig für SPF); falls der Server das nicht erlaubt, ohne versuchen
    $ok = @mail($an, $betreff, $text, $header, '-f' . MAIL_FROM);
    if (!$ok) {
        $ok = @mail($an, $betreff, $text, $header);
    }
    return $ok;
}

// ---------- Anfrage prüfen ----------
if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    header('Allow: POST');
    fehler(405, 'Nur POST erlaubt.');
}

$origin = $_SERVER['HTTP_ORIGIN'] ?? '';
if ($origin !== '' && !preg_match('#^https://(www\.)?itconaix\.de$#', $origin)) {
    fehler(403, 'Anfrage von einer fremden Seite abgelehnt.');
}

$in = json_decode((string) file_get_contents('php://input', false, null, 0, 20000), true);
if (!is_array($in)) {
    fehler(400, 'Die Anfrage war unvollständig. Bitte versucht es noch einmal.');
}

// Bots: unsichtbares Feld ausgefüllt oder zu schnell abgeschickt -> still "erfolgreich", es passiert nichts
if (feld($in, 'xq_c', 200) !== '') {
    antwort(200, ['ok' => true, 'confirm' => false]);
}
// Ausfülldauer misst der Browser selbst (unabhängig davon, ob seine Uhr richtig geht)
$dauer = isset($in['ms']) && is_numeric($in['ms']) ? (float) $in['ms'] : 0.0;
if ($dauer > 0 && $dauer < MIN_FILL_MS) {
    antwort(200, ['ok' => true, 'confirm' => false]);
}

$typ = feld($in, 'type', 20);
if (!in_array($typ, ['termin', 'nachricht'], true)) {
    fehler(400, 'Unbekannte Anfrage.');
}

$name  = einzeilig(feld($in, 'name', 100));
$email = einzeilig(feld($in, 'email', 150));
$text  = feld($in, 'text', 4000);

if ($name === '') {
    fehler(422, 'Bitte tragt euren Namen ein.');
}
if (!filter_var($email, FILTER_VALIDATE_EMAIL)) {
    fehler(422, 'Bitte tragt eine gültige E-Mail-Adresse ein.');
}
if ($typ === 'nachricht' && $text === '') {
    fehler(422, 'Bitte schreibt uns kurz, worum es geht.');
}

$firma = $telefon = $thema = $art = '';
$termin = null;
if ($typ === 'termin') {
    $firma   = einzeilig(feld($in, 'firma', 120));
    $telefon = einzeilig(feld($in, 'telefon', 40));
    if ($telefon !== '' && !preg_match('/^[0-9+()\/\- ]{5,40}$/', $telefon)) {
        fehler(422, 'Die Telefonnummer enthält ungültige Zeichen.');
    }
    $thema = feld($in, 'thema', 60);
    if (!in_array($thema, THEMEN, true)) {
        $thema = 'Etwas anderes';
    }
    $art = feld($in, 'kind', 20);
    if (!in_array($art, KINDS, true)) {
        fehler(422, 'Bitte wählt Videocall oder Telefon.');
    }

    $datum = feld($in, 'date', 10);
    $zeit  = feld($in, 'time', 5);
    if (!preg_match('/^\d{4}-\d{2}-\d{2}$/', $datum) || !preg_match('/^\d{2}:\d{2}$/', $zeit)) {
        fehler(422, 'Bitte wählt einen Tag und eine Uhrzeit.');
    }
    $termin = DateTimeImmutable::createFromFormat('!Y-m-d H:i', $datum . ' ' . $zeit, new DateTimeZone('Europe/Berlin'));
    if (!$termin || $termin->format('Y-m-d H:i') !== $datum . ' ' . $zeit) {
        fehler(422, 'Dieses Datum gibt es nicht.');
    }
    $minuten   = (int) $termin->format('G') * 60 + (int) $termin->format('i');
    $wochentag = (int) $termin->format('N');
    $jetzt     = new DateTimeImmutable('now', new DateTimeZone('Europe/Berlin'));
    $grenze    = $jetzt->setTime(23, 59)->modify('+' . DAYS_AHEAD . ' days');
    if ($wochentag > 5 || $minuten < SLOT_FROM || $minuten >= SLOT_TO || ($minuten - SLOT_FROM) % SLOT_MIN !== 0) {
        fehler(422, 'Termine gibt es werktags zwischen 12 und 19 Uhr. Bitte wählt eine andere Zeit.');
    }
    // eine Stunde Toleranz gegenüber der Website (Zeitzonen, Uhr des Besuchers)
    if ($termin < $jetzt->modify('+' . (LEAD_HOURS - 1) . ' hours') || $termin > $grenze) {
        fehler(422, 'Dieser Termin ist nicht mehr verfügbar. Bitte wählt einen anderen Tag.');
    }
}

// ---------- Missbrauchsschutz: höchstens RATE_MAX Anfragen pro Stunde ----------
$ordner = rtrim(sys_get_temp_dir(), '/\\') . '/itconaix-anfragen';
if (!is_dir($ordner)) {
    @mkdir($ordner, 0700, true);
}
$datei = $ordner . '/' . hash('sha256', ($_SERVER['REMOTE_ADDR'] ?? '') . '|itconaix');
$jetztTs = time();
$treffer = [];
if (is_file($datei)) {
    $alt = json_decode((string) @file_get_contents($datei), true);
    if (is_array($alt)) {
        $treffer = array_values(array_filter($alt, static function ($ts) use ($jetztTs) {
            return is_int($ts) && $ts > $jetztTs - RATE_WINDOW;
        }));
    }
}
if (count($treffer) >= RATE_MAX) {
    fehler(429, 'Ihr habt gerade schon mehrere Anfragen geschickt. Bitte versucht es später noch einmal oder schreibt direkt an ' . MAIL_TO . '.');
}
$treffer[] = $jetztTs;
@file_put_contents($datei, json_encode($treffer), LOCK_EX);
// gelegentlich alte Einträge aufräumen
if (random_int(1, 50) === 1) {
    $liste = glob($ordner . '/*');
    foreach ((is_array($liste) ? $liste : []) as $f) {
        if (is_file($f) && filemtime($f) < $jetztTs - RATE_WINDOW) {
            @unlink($f);
        }
    }
}

// ---------- E-Mail an das Team ----------
$antwortAn = kopf($name) . ' <' . $email . '>';
if ($typ === 'termin') {
    $wann    = datumLang($termin) . ', ' . $termin->format('H:i') . ' Uhr';
    $betreff = 'Terminanfrage: ' . $wann . ' – ' . $name;
    $zeilen  = [
        'Neue Terminanfrage über itconaix.de',
        '',
        'Wunschtermin:  ' . $wann . ' (30 Minuten)',
        'Gesprächsart:  ' . $art,
        'Thema:         ' . $thema,
        '',
        'Name:          ' . $name,
        'Unternehmen:   ' . ($firma !== '' ? $firma : '–'),
        'E-Mail:        ' . $email,
        'Telefon:       ' . ($telefon !== '' ? $telefon : '–'),
        '',
        'Zum Vorhaben:',
        $text !== '' ? $text : '–',
        '',
        '—',
        'Mit "Antworten" schreibt ihr direkt an ' . $email . '.',
        'Bitte den Termin bestätigen oder eine andere Zeit vorschlagen.',
    ];
} else {
    $betreff = 'Nachricht über die Website – ' . $name;
    $zeilen  = [
        'Neue Nachricht über itconaix.de',
        '',
        'Name:    ' . $name,
        'E-Mail:  ' . $email,
        '',
        $text,
        '',
        '—',
        'Mit "Antworten" schreibt ihr direkt an ' . $email . '.',
    ];
}
if (!sende(MAIL_TO, $betreff, implode("\n", $zeilen), $antwortAn)) {
    fehler(500, 'Die Anfrage konnte gerade nicht gesendet werden. Bitte schreibt uns direkt an ' . MAIL_TO . '.');
}

// ---------- Eingangsbestätigung an den Absender ----------
// Bewusst ohne eingegebene Texte, damit das Formular nicht zum Versenden fremder Inhalte missbraucht werden kann.
$bestaetigung = ['Guten Tag,', '', 'vielen Dank für eure Anfrage. Sie ist bei uns angekommen.', ''];
if ($typ === 'termin') {
    $bestaetigung[] = 'Euer Wunschtermin: ' . datumLang($termin) . ', ' . $termin->format('H:i') . ' Uhr (' . $art . ', 30 Minuten)';
    $bestaetigung[] = '';
    $bestaetigung[] = 'Der Termin ist damit noch nicht fest gebucht. Wir prüfen ihn und melden uns am selben Werktag mit einer Bestätigung oder einem anderen Vorschlag.';
} else {
    $bestaetigung[] = 'Wir melden uns am selben Werktag bei euch.';
}
array_push(
    $bestaetigung,
    '',
    'Falls ihr noch etwas ergänzen wollt, antwortet einfach auf diese E-Mail.',
    '',
    'Viele Grüße',
    'IT conAIX',
    MAIL_TO . ' · ' . SITE_URL,
    '',
    '—',
    'Diese E-Mail wurde automatisch verschickt, weil mit dieser Adresse auf ' . SITE_URL . ' eine Anfrage gestellt wurde. Falls das nicht von euch kam, könnt ihr sie einfach ignorieren.'
);
$bestaetigt = sende($email, $typ === 'termin' ? 'Eure Terminanfrage bei IT conAIX' : 'Eure Nachricht an IT conAIX', implode("\n", $bestaetigung), kopf('IT conAIX') . ' <' . MAIL_TO . '>');

antwort(200, ['ok' => true, 'confirm' => $bestaetigt]);
