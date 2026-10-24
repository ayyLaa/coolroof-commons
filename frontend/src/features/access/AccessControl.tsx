import { Button, Group, Modal, PasswordInput, Stack, Text } from '@mantine/core'
import { useState } from 'react'
import type { ReactNode } from 'react'
import { operatorToken, storeOperatorToken } from '../../api/auth'

export function AccessControl(): ReactNode {
  const [open, setOpen] = useState(false)
  const [token, setToken] = useState(operatorToken)
  return (
    <>
      <Button variant="subtle" size="xs" onClick={() => setOpen(true)}>
        Operator access
      </Button>
      <Modal opened={open} onClose={() => setOpen(false)} title="Operator access">
        <Stack>
          <Text size="sm">
            Enter the operator key for protected measurement, reset and payment requests. It stays
            in this browser tab's session.
          </Text>
          <PasswordInput
            label="Operator key"
            value={token}
            onChange={event => setToken(event.currentTarget.value)}
          />
          <Group>
            <Button
              onClick={() => {
                storeOperatorToken(token.trim())
                setOpen(false)
              }}
            >
              Save access
            </Button>
            <Button
              variant="subtle"
              onClick={() => {
                storeOperatorToken('')
                setToken('')
                setOpen(false)
              }}
            >
              Clear access
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  )
}
