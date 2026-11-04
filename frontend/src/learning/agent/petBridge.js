// The pet is a view of the shared session, never a second conversation.
export function latestPetTurn(messages = []) {
  let start = -1
  for (let index = messages.length - 1; index >= 0; index--) {
    if (messages[index].role === 'user') { start = index; break }
  }
  if (start < 0) return { id: null, question: '', replies: [] }
  return {
    id: messages[start].id,
    question: messages[start].content,
    replies: messages.slice(start + 1).filter(message => message.role === 'assistant'),
  }
}

export function connectPetSession(session, pet, update) {
  const source = 'teaching-session'
  let phase = null
  let token
  const unsubscribe = session.subscribe(snapshot => {
    update(snapshot)
    if (snapshot.phase === phase) return
    phase = snapshot.phase
    if (phase === 'working') token = pet.begin(source, { label: '教学辅导师' })
    else if (phase === 'complete' || phase === 'error') {
      // Mounting a view on an already settled session must not invent a request.
      if (token !== undefined) {
        if (phase === 'complete') pet.complete(source, token)
        else pet.fail(source, token)
      }
    } else {
      pet.clear(source, token)
      token = undefined
    }
  })
  return () => { unsubscribe(); pet.clear(source, token) }
}
