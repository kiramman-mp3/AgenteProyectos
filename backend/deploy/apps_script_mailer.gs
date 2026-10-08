/**
 * Relé de correo para el Agente de Proyectos (Render gratuito bloquea SMTP, pero permite HTTPS).
 * Envía los avisos desde la cuenta de Gmail que publica este script.
 *
 * Instalación:
 *  1. https://script.google.com → Nuevo proyecto → pega este código.
 *  2. Configuración del proyecto (⚙) → Propiedades del script → agrega SECRET con el valor de MAIL_WEBHOOK_SECRET.
 *  3. Implementar → Nueva implementación → tipo "Aplicación web":
 *       Ejecutar como: Yo · Quién tiene acceso: Cualquier usuario → Implementar → autoriza los permisos.
 *  4. Copia la URL de la aplicación web (termina en /exec) en MAIL_WEBHOOK_URL del backend.
 */
function doPost(e) {
  var secret = PropertiesService.getScriptProperties().getProperty('SECRET');
  var data;
  try {
    data = JSON.parse(e.postData.contents);
  } catch (err) {
    return respond({ ok: false, error: 'JSON inválido' });
  }
  if (!secret || data.secret !== secret) {
    return respond({ ok: false, error: 'no autorizado' });
  }
  MailApp.sendEmail({
    to: data.to,
    subject: data.subject,
    body: data.body,
    htmlBody: data.htmlBody || undefined,
    name: 'Agente de Proyectos',
  });
  return respond({ ok: true });
}

function respond(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
