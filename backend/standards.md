# Estándares de programación del proyecto

Edita este archivo con las normas propias de tu equipo. El Agente Ejecutor las usa para evaluar cada cambio.

1. **Nombres claros**: variables, funciones y clases con nombres descriptivos; convenciones del lenguaje (camelCase en JS/TS, snake_case en Python, PascalCase para clases).
2. **Funciones pequeñas**: una responsabilidad por función; evitar funciones de más de ~50 líneas o con más de 4 niveles de anidación.
3. **Sin duplicación**: lógica repetida debe extraerse a funciones o módulos reutilizables (principio DRY).
4. **Manejo de errores**: no silenciar excepciones; validar entradas externas; mensajes de error útiles.
5. **Seguridad**: nunca incluir credenciales, tokens o contraseñas en el código; usar consultas parametrizadas (evitar inyección SQL); sanitizar entradas del usuario (XSS); no usar `eval`.
6. **Rendimiento**: evitar consultas dentro de bucles (N+1), operaciones costosas repetidas y cargas innecesarias.
7. **Legibilidad**: comentarios solo donde aportan; código formateado de forma consistente; sin código muerto ni comentado.
8. **Pruebas**: la lógica de negocio nueva debe ir acompañada de pruebas unitarias.
9. **Commits**: mensajes descriptivos; cambios pequeños y enfocados.
