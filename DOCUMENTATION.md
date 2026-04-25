# Documentació d'Arquitectura i API — HackUPC 2026 Mecalux

Aquest document explica extensament com funciona la plataforma que hem creat. Actua com a "pont" entre l'algoritme d'optimització (Backend) i la interfície visual (Frontend).

---

## 1. Visió General de la Interacció

El sistema està dissenyat per ser ràpid, interactiu i eliminar qualsevol complexitat innecessària.

1. **El Frontend (Web)** no es comunica directament amb l'algoritme del teu company. Es comunica sempre amb la **teva API (FastAPI)**.
2. **La teva API** és l'encarregada de:
   - Validar les dades i els CSVs.
   - Calcular la puntuació (Heurística Q) de manera ultra-ràpida (< 5ms).
   - Comprovar si les estanteries xoquen amb parets o obstacles.
   - Executar l'algoritme d'optimització pesat en segon pla (background) i anar avisant a la web del % de progrés.
3. **L'Optimizer (Backend del company)** només és una funció matemàtica. Rep unes llistes netes (x, y, amplada...) i retorna una llista de posicions on col·locar les estanteries.

---

## 2. Què fa cada fitxer? (I on tocar si hi ha un error)

Si hi ha un error, depenent del que falli, hauràs de mirar un fitxer o un altre. Tots els fitxers estan dins la carpeta `api/`.

### `models.py`
- **Què fa:** Defineix l'estructura exacta de totes les dades que entren i surten de l'API (els "Pydantic Models"). Aquí es defineix com és una Estanteria (`BayType`), un Obstacle, el resultat (`SolveResult`), etc.
- **Quan tocar-lo:** Si decidiu que l'algoritme ha de retornar algun camp nou (per exemple, el "temps total" o una llista extra), o si us adoneu que falta algun camp del CSV.

### `csv_parser.py`
- **Què fa:** Llegeix els textos dels 4 fitxers CSV i els converteix a diccionaris i llistes de Python.
- **Quan tocar-lo:** Si quan el Frontend puja els CSVs dóna un "CSV parsing error". Això passa si Mecalux canvia el format d'algun CSV de sobte (per exemple, si afegeixen una nova columna a `types_of_bays.csv`).

### `scorer.py`
- **Què fa:** Conté totes les matemàtiques geomètriques. Calcula l'àrea, detecta si un punt està dins del magatzem, si dues estanteries xoquen (overlap) i, sobretot, **calcula la puntuació Q**.
- **Quan tocar-lo:** Si el Frontend diu que el score calculat no quadra amb el que s'esperava, o si l'API detecta col·lisions on no n'hi ha.

### `job_store.py`
- **Què fa:** És la nostra "base de dades" falsa. Guarda a la memòria RAM els treballs (`jobs`) que s'estan executant i el seu percentatge de progrés.
- **Quan tocar-lo:** Gairebé mai. És pura infraestructura.

### `routes.py`
- **Què fa:** És el "recepcionista". Defineix les URLs de l'API (ex: `POST /api/v1/score` o `GET /api/v1/health`) i decideix quina funció s'ha d'executar quan algú hi entra.
- **Quan tocar-lo:** Si necessiteu crear una URL nova per la pàgina web o si canvieu el comportament d'algun endpoint.

### `main.py`
- **Què fa:** Arrenca el servidor FastAPI i configura el CORS perquè el navegador web no bloquegi les peticions per motius de seguretat.
- **Quan tocar-lo:** Només si necessiteu canviar el port on s'executa el servidor.

---

## 3. Com l'ha d'utilitzar el Frontend (Explicació per l'equip Web)

L'equip de frontend té dos casos d'ús principals.

### Cas A: Mode Interactiu (L'usuari arrossega peces amb el ratolí)
Això és el que dóna l'efecte "WOW" al projecte.
1. L'usuari mou una estanteria a la pantalla.
2. El Frontend fa un **`POST /api/v1/score`**.
   - **INPUT:** Un JSON amb la posició de totes les estanteries (`placed_bays`), els tipus disponibles, les coordenades del magatzem, els obstacles i el sostre.
   - **OUTPUT:** L'API respon a l'instant amb: `{"Q": 318.0, "is_valid": false, "issues": [{"message": "Bay 0 collides with obstacle"}]}`.
3. El Frontend utilitza això per pintar el score actualitzat a dalt de la pantalla i posar de color vermell les estanteries que tinguin "issues".

### Cas B: Mode Automàtic (L'algoritme fa la feina)
1. L'usuari fa click a "Upload CSVs & Solve".
2. El Frontend fa un **`POST /api/v1/solve`** enviant els 4 fitxers CSV com a *multipart/form-data*.
   - **OUTPUT:** L'API respon immediatament donant un ID: `{"job_id": "1234-abcd", "status": "QUEUED"}`.
3. El Frontend s'enganxa a l'endpoint de streaming de text: **`GET /api/v1/jobs/1234-abcd/stream`**.
   - **OUTPUT:** Això no és una resposta normal. És un "tub" (SSE - Server Sent Events) obert on l'API anirà escopint missatges:
     `data: {"event": "job_progress", "percent": 20}`
     `data: {"event": "job_progress", "percent": 50}`
4. Quan l'algoritme acaba, escup: `data: {"event": "job_completed", "result": {"placed_bays": [...], "Q": 123.4}}`.
5. El Frontend rep això i pinta les peces a la pantalla.

---

## 4. Com l'ha d'utilitzar el Backend (L'equip d'algorísmia)

El teu company **NO** ha de tocar l'API. Ell només ha de modificar un sol fitxer: `optimizer/solver.py`.

1. Dins d'aquest fitxer hi ha una funció anomenada `solve(...)`.
2. Ell rebrà les llistes totalment netes (ja sense CSVs, només llistes de diccionaris).
3. A mesura que el seu codi (per exemple un loop o un algoritme genètic) vagi pensant, ha de cridar la funció `on_progress(percentatge, missatge)`. Per exemple: `on_progress(30, "Calculant poblacio 5...")`.
4. En acabar, només ha de retornar un diccionari amb les posicions escollides (`placed_bays`), la `Q` obtinguda i el temps. Tot el procés de fer arribar això a la web ho fa la teva API màgicament.
